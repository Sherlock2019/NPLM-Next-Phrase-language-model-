"""Semantic role engine (spec sections 17-18).

Turns a dependency relation into a *distribution* over universal semantic roles,
never a hard assignment. Evidence is combined multiplicatively:

    P(role) ∝ prior(deprel, predicate_type)
              × adposition_cue(role)
              × subordinator_cue(role)
              × predicate_profile(lemma, deprel)(role)
              × entity_boost(entity_type)(role)
              × adverb_class_cue(role)

Every factor comes from a YAML file. The engine contains the arithmetic and the
evidence-gathering, not the linguistic facts.

Crucially (spec section 18) role assignment is predicate-specific: the object of
``meet`` is a PARTICIPANT while the object of ``deploy`` is a PATIENT, and no
ARG0/ARG1 shortcut is assumed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

from pydantic import BaseModel, Field

from splm.language.packs import LanguagePack, LanguagePackRegistry, UniversalPack, get_registry
from splm.linguistic.parser import ParsedSentence, Token

logger = logging.getLogger(__name__)

#: Relations whose dependent is consumed as evidence rather than given a role.
MARKER_DEPRELS = frozenset({"case", "mark", "cop", "aux", "det", "cc", "punct", "expl"})


class RoleHypothesis(BaseModel):
    """One candidate role with the evidence that supported it."""

    role: str
    probability: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)


class RoleAssignment(BaseModel):
    """The ranked role hypotheses for one dependent of a predicate."""

    token_index: int
    deprel: str
    text: str
    head_lemma: str
    hypotheses: list[RoleHypothesis] = Field(default_factory=list)
    annotations: dict[str, Any] = Field(
        default_factory=dict,
        description="Extra structured facts, e.g. {'transport': 'train'}",
    )
    is_modifier: bool = False
    is_nested: bool = False

    @property
    def best(self) -> RoleHypothesis | None:
        return self.hypotheses[0] if self.hypotheses else None

    @property
    def role(self) -> str | None:
        return self.hypotheses[0].role if self.hypotheses else None

    @property
    def confidence(self) -> float:
        return self.hypotheses[0].probability if self.hypotheses else 0.0

    @property
    def margin(self) -> float:
        """How far ahead the winner is. A small margin means a genuine ambiguity."""
        if len(self.hypotheses) < 2:
            return self.confidence
        return self.hypotheses[0].probability - self.hypotheses[1].probability

    @property
    def alternatives(self) -> list[RoleHypothesis]:
        return self.hypotheses[1:]


@dataclass
class _Cue:
    """One multiplicative evidence source.

    ``default`` is what a role absent from ``distribution`` receives, and the
    distinction matters more than it looks:

    * A **distribution** cue (an adposition, a subordinator) is a probability
      distribution over roles, so a role it never mentions is genuinely unlikely and
      gets the floor.
    * A **multiplier** cue (a named-entity boost) says only "this role is more or less
      likely than the prior said". A role it does not mention must be left alone, so it
      gets 1.0. Giving it the floor instead would turn every boost table into a veto
      over the roles it happens not to list.
    """

    name: str
    distribution: dict[str, float]
    annotations: dict[str, Any] = field(default_factory=dict)
    default: float | None = None


class SemanticRoleEngine:
    """Assigns universal semantic roles to the dependents of a predicate."""

    def __init__(
        self,
        registry: LanguagePackRegistry | None = None,
        *,
        propbank: Any | None = None,
    ) -> None:
        self._registry = registry or get_registry()
        # Optional PropBank adapter; when present it contributes a predicate-specific
        # cue built from each roleset's argument descriptors (never a fixed ARGn map).
        self._propbank = propbank

    @property
    def universal(self) -> UniversalPack:
        return self._registry.universal()

    def _pack(self, language: str) -> LanguagePack:
        return self._registry.get(language)

    # -- public API --------------------------------------------------------

    def assign_all(
        self,
        sentence: ParsedSentence,
        predicate: Token,
        predicate_type: str | None = None,
    ) -> list[RoleAssignment]:
        """Assign roles to every role-bearing dependent of ``predicate``."""
        assignments: list[RoleAssignment] = []
        by_index: dict[int, RoleAssignment] = {}

        pack = self._pack(sentence.language)
        for dependent in sentence.children(predicate.index):
            if (
                self._is_marker(dependent)
                or self._is_negation(dependent, pack)
                or self._is_grammatical_particle(dependent, pack)
            ):
                continue
            assignment = self.assign(sentence, predicate, dependent, predicate_type)
            if assignment is None:
                continue
            assignments.append(assignment)
            by_index[dependent.index] = assignment

        # Coordinated elements inherit the role of the conjunct they hang off.
        assignments.extend(self._inherit_conjuncts(sentence, by_index))
        assignments.sort(key=lambda a: a.token_index)
        return assignments

    def assign(
        self,
        sentence: ParsedSentence,
        predicate: Token | None,
        dependent: Token,
        predicate_type: str | None = None,
        *,
        deprel_override: str | None = None,
    ) -> RoleAssignment | None:
        """Compute the role distribution for one dependent.

        ``deprel_override`` lets a caller ask "what role would this constituent play
        if it were an oblique?" - needed for copular complements, which are the
        clause's syntactic head and so carry ``root`` rather than a role-bearing
        relation.
        """
        universal = self.universal
        pack = self._pack(sentence.language)
        deprel = deprel_override or dependent.deprel

        prior, prior_source = self._prior_for(
            universal, pack, predicate, dependent, deprel, predicate_type
        )
        if not prior:
            logger.debug("no prior for deprel %r; skipping word %d", deprel, dependent.index)
            return None

        cues = list(self._gather_cues(sentence, pack, universal, predicate, dependent))
        distribution, evidence = self._combine(prior, cues, universal.floor)

        annotations: dict[str, Any] = {}
        for cue in cues:
            annotations.update(cue.annotations)

        for role_evidence in evidence.values():
            role_evidence.insert(0, f"prior_source={prior_source}")

        hypotheses = [
            RoleHypothesis(role=role, probability=round(prob, 4), evidence=evidence.get(role, []))
            for role, prob in sorted(distribution.items(), key=lambda kv: kv[1], reverse=True)
            if prob > 0.0
        ]

        return RoleAssignment(
            token_index=dependent.index,
            deprel=deprel,
            text=sentence.subtree_text(dependent.index, exclude=universal.nested_deprels),
            head_lemma=dependent.lower_lemma,
            hypotheses=hypotheses[:6],
            annotations=annotations,
            is_modifier=universal.is_modifier_deprel(deprel),
            is_nested=deprel in universal.nested_deprels
            or dependent.base_deprel in universal.nested_deprels,
        )

    # -- prior selection ---------------------------------------------------

    def _prior_for(
        self,
        universal: UniversalPack,
        pack: LanguagePack,
        predicate: Token | None,
        dependent: Token,
        deprel: str,
        predicate_type: str | None,
    ) -> tuple[dict[str, float], str]:
        """Choose the starting distribution for a dependent.

        Predicate-specific knowledge *replaces* the generic relation prior rather than
        multiplying into it. That is what it means for roles to be predicate-specific
        (spec section 18): if the lexicon says the object of *meet* is a PARTICIPANT,
        the generic "objects are usually patients" prior is not also true - it has been
        superseded for this predicate.

        Multiplying the two instead makes the system depend on an accident. The generic
        prior would keep PATIENT high, and only an unrelated cue - a named-entity boost
        that happens not to list PATIENT - would pull it back down. That works in a
        language with an NER model and silently fails in one without, which is exactly
        what happened to Vietnamese before this was fixed.
        """
        if predicate is not None:
            if self._propbank is not None:
                propbank = self._propbank_cue(predicate, dependent)
                if propbank:
                    return propbank, f"propbank:{predicate.lower_lemma}"

            profile = self._predicate_profile(
                pack, predicate, dependent, universal=universal
            )
            if profile:
                return profile, f"predicate_profile:{predicate.lower_lemma}"

        prior = universal.deprel_prior(deprel, predicate_type)
        if not prior:
            prior = universal.deprel_prior(dependent.base_deprel, predicate_type)
        return prior, f"deprel:{deprel}"

    # -- evidence ----------------------------------------------------------

    def _gather_cues(
        self,
        sentence: ParsedSentence,
        pack: LanguagePack,
        universal: UniversalPack,
        predicate: Token | None,
        dependent: Token,
    ) -> Iterable[_Cue]:
        """Collect every applicable evidence source for one dependent."""
        adposition = self._adposition_of(sentence, dependent)
        entity_type = self._entity_type_of(sentence, dependent)

        # 1. Lexical overrides win over the plain adposition cue: "by train" is HOW,
        #    not USING WHAT, even though `by` usually suggests an instrument.
        override = self._lexical_override(pack, dependent, adposition, entity_type)
        if override is not None:
            yield override
        elif adposition is not None:
            fixed = self._fixed_adposition(sentence, adposition)
            cue = pack.fixed_adposition_cue(fixed) if fixed else {}
            if cue:
                yield _Cue(f"fixed_adposition:{fixed}", cue)
            else:
                cue = pack.adposition_cue(adposition.lower_lemma)
                if cue:
                    yield _Cue(f"adposition:{adposition.lower_lemma}", cue)

        # 2. Subordinator on a clausal dependent: if / because / to / when.
        marker = sentence.child_by_deprel(dependent.index, "mark")
        if marker is not None:
            cue = pack.subordinator_cue(marker.lower_lemma)
            if cue:
                yield _Cue(f"subordinator:{marker.lower_lemma}", cue)

        # 3. Predicate-specific argument structure is applied as the *prior*, in
        #    _prior_for, not as a cue. See the reasoning there.

        # 4. Clause head that behaves like an adposition: "using Terraform".
        clause_cue = self._clause_head_cue(pack, sentence, dependent)
        if clause_cue is not None:
            yield clause_cue

        # 5. Bare adverbials with no adposition: "yesterday", "here", "quickly".
        adverb_cue = self._adverb_cue(pack, dependent)
        if adverb_cue:
            yield _Cue(f"adverb_class:{dependent.lower_lemma}", adverb_cue)

        # 6. Named-entity type. A multiplier, not a distribution: it adjusts the roles
        #    it names and says nothing about the rest.
        boost = universal.entity_role_boost(entity_type)
        if boost:
            yield _Cue(f"entity:{entity_type}", boost, default=1.0)

    def _combine(
        self, prior: dict[str, float], cues: list[_Cue], floor: float
    ) -> tuple[dict[str, float], dict[str, list[str]]]:
        """Multiply prior by every cue, then renormalise."""
        roles = set(prior)
        for cue in cues:
            roles.update(cue.distribution)

        scores: dict[str, float] = {}
        evidence: dict[str, list[str]] = {}

        for role in roles:
            score = prior.get(role, floor)
            trail = [f"prior={prior.get(role, floor):.3f}"]
            for cue in cues:
                # A distribution cue that never mentions a role contributes the floor,
                # not zero: one silent evidence source must not veto a role outright.
                # A multiplier cue contributes 1.0 instead - see _Cue.
                fallback = floor if cue.default is None else cue.default
                factor = cue.distribution.get(role, fallback)
                score *= factor
                if factor != fallback:
                    trail.append(f"{cue.name}={factor:.2f}")
            scores[role] = score
            evidence[role] = trail

        total = sum(scores.values())
        if total <= 0:
            uniform = 1.0 / max(len(scores), 1)
            return {role: uniform for role in scores}, evidence
        return {role: score / total for role, score in scores.items()}, evidence

    # -- individual cue sources -------------------------------------------

    @staticmethod
    def _is_marker(token: Token) -> bool:
        return token.deprel in MARKER_DEPRELS or token.base_deprel in MARKER_DEPRELS

    @staticmethod
    def _is_grammatical_particle(token: Token, pack: LanguagePack) -> bool:
        """Whether a dependent is a tense/aspect/modality particle, not a role bearer.

        Relation labels alone are not enough here. English marks the future with an
        auxiliary that parsers label ``aux``, so it is filtered by relation. Vietnamese
        marks it with a preverbal particle - ``se``, ``dang``, ``da`` - that the VTB
        parser tags ADV/``advmod``, which would otherwise be read as HOW. The language
        pack already lists these words as auxiliaries; that list is the authority,
        whatever relation the parser assigned.
        """
        if not pack.auxiliary_spec(token.lower_lemma):
            return False
        return token.base_deprel in {"advmod", "aux", "dep", "mark", "discourse", "compound"}

    @staticmethod
    def _is_negation(token: Token, pack: LanguagePack) -> bool:
        """Whether a dependent is a negation marker rather than a role bearer.

        UD attaches ``not`` as ``advmod``, which would otherwise be read as HOW.
        Negation is recorded on the frame's ``negation`` field instead.
        """
        if token.feat("Polarity") == "Neg":
            return True
        return token.base_deprel in {"advmod", "aux", "dep", "part"} and (
            token.lower_lemma in pack.negation_particles
        )

    @staticmethod
    def _adposition_of(sentence: ParsedSentence, dependent: Token) -> Token | None:
        return sentence.child_by_deprel(dependent.index, "case")

    @staticmethod
    def _fixed_adposition(sentence: ParsedSentence, adposition: Token) -> str | None:
        """Rebuild a multi-word adposition such as ``because of`` from its chain."""
        parts = [adposition.lower_lemma]
        parts.extend(
            child.lower_lemma
            for child in sentence.children(adposition.index)
            if child.base_deprel in {"fixed", "flat", "goeswith"}
        )
        return " ".join(parts) if len(parts) > 1 else None

    def _entity_type_of(self, sentence: ParsedSentence, dependent: Token) -> str | None:
        """Entity type of the constituent, read off its head or its proper nouns."""
        if dependent.entity_type:
            return dependent.entity_type
        for child in sentence.children(dependent.index):
            if child.base_deprel in {"flat", "compound", "appos"} and child.entity_type:
                return child.entity_type
        return None

    def _lexical_override(
        self,
        pack: LanguagePack,
        dependent: Token,
        adposition: Token | None,
        entity_type: str | None,
    ) -> _Cue | None:
        """Apply a language pack's `lexical_overrides` rule if one matches."""
        for rule in pack.lexical_overrides:
            wanted_adp = rule.get("adposition")
            if wanted_adp and (adposition is None or adposition.lower_lemma != wanted_adp):
                continue

            wanted_class = rule.get("head_lemma_in_class")
            if wanted_class and dependent.lower_lemma not in pack.semantic_class_members(
                wanted_class
            ):
                continue

            wanted_entity = rule.get("head_entity_type")
            if wanted_entity and entity_type != wanted_entity:
                continue

            distribution = {k: float(v) for k, v in (rule.get("distribution") or {}).items()}
            if not distribution:
                continue

            annotations = {
                key: str(value).replace("{head_lemma}", dependent.lower_lemma)
                for key, value in (rule.get("annotate") or {}).items()
            }
            return _Cue(f"override:{rule.get('name', 'unnamed')}", distribution, annotations)
        return None

    @staticmethod
    def _predicate_profile(
        pack: LanguagePack,
        predicate: Token,
        dependent: Token,
        *,
        universal: UniversalPack | None = None,
    ) -> dict[str, float]:
        """Per-verb argument structure from the language pack.

        This is the hand-written stand-in for PropBank frame files: which role this
        particular predicate gives to this particular relation.

        A profile entry for a *base* relation does not apply to a subtyped one that has
        its own prior. ``deploy`` lists ``obl`` as a destination, but the ``obl:agent``
        of a passive is an agent regardless of the verb - letting the generic entry win
        there would turn "deployed by the engineer" into a destination.
        """
        profiles = pack.syntax.get("predicate_role_profiles", {}) or {}
        profile = profiles.get(predicate.lower_lemma)
        if not profile:
            return {}

        by_deprel = profile.get(dependent.deprel)
        if by_deprel is None:
            subtyped_and_specific = (
                dependent.deprel != dependent.base_deprel
                and universal is not None
                and universal.has_exact_prior(dependent.deprel)
            )
            if not subtyped_and_specific:
                by_deprel = profile.get(dependent.base_deprel)

        return {k: float(v) for k, v in (by_deprel or {}).items()}

    def _propbank_cue(self, predicate: Token, dependent: Token) -> dict[str, float]:
        """Ask the PropBank adapter for a predicate-specific role distribution."""
        try:
            return self._propbank.role_distribution(
                lemma=predicate.lower_lemma, deprel=dependent.deprel
            )
        except Exception as exc:  # pragma: no cover - adapter is optional
            logger.debug("propbank lookup failed for %s: %s", predicate.lower_lemma, exc)
            return {}

    @staticmethod
    def _clause_head_cue(
        pack: LanguagePack, sentence: ParsedSentence, dependent: Token
    ) -> _Cue | None:
        """Clause heads that function like adpositions, e.g. ``using X``."""
        cues = pack.syntax.get("clause_head_cues", {}) or {}
        spec = cues.get(dependent.lower_lemma)
        if not spec:
            return None
        distribution = {k: float(v) for k, v in (spec.get("distribution") or {}).items()}
        if not distribution:
            return None
        annotations: dict[str, Any] = {}
        if spec.get("promote_object"):
            obj = sentence.child_by_deprel(dependent.index, "obj")
            if obj is not None:
                # The instrument is Terraform, not "using".
                annotations["promote_to"] = obj.index
        return _Cue(f"clause_head:{dependent.lower_lemma}", distribution, annotations)

    @staticmethod
    def _adverb_cue(pack: LanguagePack, dependent: Token) -> dict[str, float]:
        """Classify a bare adverb or bare temporal noun."""
        lemma = dependent.lower_lemma
        if lemma in pack.temporal_adverbs:
            return {"TIME": 0.95}
        if lemma in pack.locative_adverbs:
            return {"LOCATION": 0.95}
        if lemma in pack.manner_adverbs:
            return {"MANNER": 0.9}
        if dependent.upos == "ADV":
            suffixes = pack.syntax.get("manner_adverb_suffixes", []) or []
            if any(lemma.endswith(str(suffix)) for suffix in suffixes):
                return {"MANNER": 0.8}
        return {}

    def _inherit_conjuncts(
        self, sentence: ParsedSentence, assigned: dict[int, RoleAssignment]
    ) -> list[RoleAssignment]:
        """Give each coordinated element the role of its conjunct head.

        "John met Sarah and Mary" - Mary hangs off Sarah, not the verb, but plays
        the same role.
        """
        inherited: list[RoleAssignment] = []
        for index, assignment in list(assigned.items()):
            for conjunct in sentence.children_by_deprel(index, "conj"):
                if conjunct.index in assigned:
                    continue
                inherited.append(
                    RoleAssignment(
                        token_index=conjunct.index,
                        deprel=conjunct.deprel,
                        text=sentence.subtree_text(
                            conjunct.index, exclude=self.universal.nested_deprels
                        ),
                        head_lemma=conjunct.lower_lemma,
                        hypotheses=[
                            RoleHypothesis(
                                role=h.role,
                                probability=h.probability,
                                evidence=[*h.evidence, f"inherited_from={index}"],
                            )
                            for h in assignment.hypotheses
                        ],
                        annotations=dict(assignment.annotations),
                        is_modifier=assignment.is_modifier,
                        is_nested=assignment.is_nested,
                    )
                )
        return inherited

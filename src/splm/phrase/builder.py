"""Phrase Frame Builder (spec section 19) - the heart of SPLM.

Consumes a :class:`ParsedSentence` plus the knowledge layers (lexicon, morphology,
semantic roles) and produces a :class:`UniversalPhraseFrame`.

Design rules it must not break:

* **No word order is assumed** (spec section 31). The builder walks the dependency
  graph; surface position never determines a slot.
* **Nothing is flattened** (spec section 11). Conditions, purposes and reported
  content become nested frames.
* **No linguistic facts live here.** Which lemma is a STATE, which adposition means
  WHERE - all of that is in ``language_packs/``. This module holds the algorithm.
"""

from __future__ import annotations

import logging
from typing import Any

from splm.language.packs import LanguagePack, LanguagePackRegistry, UniversalPack, get_registry
from splm.linguistic.morphology import Morphology, MorphologyEngine
from splm.linguistic.parser import ParsedDocument, ParsedSentence, Token
from splm.linguistic.semantic_roles import RoleAssignment, SemanticRoleEngine
from splm.phrase.schema import (
    Aspect,
    ELEMENT_SLOTS,
    FrameElement,
    Predicate,
    PredicateType,
    RoleAlternative,
    Tense,
    UniversalPhraseFrame,
    Voice,
)

logger = logging.getLogger(__name__)

#: Dependents that are part of a constituent's meaning but not of its name.
#: Dropped from an element's surface text so the frame records "Paris", not
#: "in Paris", and "contract", not "the contract".
#:
#: ``conj`` is excluded because coordinated items become their own elements, each
#: with its own role; leaving it in would make "Sarah and Mary" one participant
#: *and* Mary a second one.
SPAN_EXCLUDE = frozenset({"case", "mark", "punct", "cc", "det", "discourse", "conj"})

#: Extra exclusions when the clause's syntactic head is itself an element - a copular
#: complement ("John is in Paris") or a bare nominal fragment ("Yesterday in Paris,").
#: Its subtree contains the whole rest of the clause, and every role-bearing dependent
#: in it is being assigned separately, so none of them belongs inside this element's
#: own text. What survives is the bare nominal: determiners, adjectives, compounds.
COMPLEMENT_SPAN_EXCLUDE = frozenset(
    {
        "cop", "nsubj", "nsubj:pass", "csubj", "aux", "aux:pass", "expl",
        "advmod", "obl", "obj", "iobj", "advcl", "acl", "xcomp", "ccomp", "nmod",
        "parataxis", "vocative", "dislocated",
    }
)

#: Guard against pathological trees.
MAX_DEPTH = 8


class PhraseFrameBuilder:
    """Builds Universal Phrase DNA from a parsed sentence."""

    def __init__(
        self,
        registry: LanguagePackRegistry | None = None,
        *,
        morphology: MorphologyEngine | None = None,
        semantic_roles: SemanticRoleEngine | None = None,
        lexicon: Any | None = None,
    ) -> None:
        self._registry = registry or get_registry()
        self.morphology = morphology or MorphologyEngine(self._registry)
        self.semantic_roles = semantic_roles or SemanticRoleEngine(self._registry)
        # Optional; when present it supplies semantic classes and definitions for
        # words the language pack does not list. Looked up per candidate, never
        # loaded wholesale (spec section 15).
        self.lexicon = lexicon

    @property
    def universal(self) -> UniversalPack:
        return self._registry.universal()

    def _pack(self, language: str) -> LanguagePack:
        return self._registry.get(language)

    # -- public API --------------------------------------------------------

    def build(
        self,
        sentence: ParsedSentence,
        *,
        style: str | None = None,
        locale: str | None = None,
    ) -> UniversalPhraseFrame:
        """Build the frame for one sentence."""
        root = sentence.root
        if root is None:
            logger.warning("no root in parsed sentence %r", sentence.text)
            return UniversalPhraseFrame(
                language=sentence.language,
                locale=locale,
                style=style,
                text=sentence.text,
                notes=["parse produced no root"],
            )
        frame = self._build_frame(sentence, root, style=style, locale=locale, depth=0)
        frame.text = sentence.text
        return frame

    def build_document(
        self, document: ParsedDocument, *, style: str | None = None, locale: str | None = None
    ) -> list[UniversalPhraseFrame]:
        return [self.build(s, style=style, locale=locale) for s in document.sentences]

    # -- frame construction ------------------------------------------------

    def _build_frame(
        self,
        sentence: ParsedSentence,
        head: Token,
        *,
        style: str | None,
        locale: str | None,
        depth: int,
        relation_to_parent: str | None = None,
    ) -> UniversalPhraseFrame:
        pack = self._pack(sentence.language)
        universal = self.universal

        predicate_head, predicate, complement, complement_deprel = self._build_predicate(
            sentence, head, pack
        )
        frame = UniversalPhraseFrame(
            language=sentence.language,
            locale=locale,
            style=style,
            predicate=predicate,
            text=sentence.subtree_text(head.index),
            token_indices=sentence.subtree_indices(head.index),
            relation_to_parent=relation_to_parent,
        )

        self._apply_grammatical_meaning(sentence, predicate_head, pack, frame)

        predicate_type = predicate.type.value if predicate else None
        assignments = self.semantic_roles.assign_all(sentence, predicate_head, predicate_type)

        for assignment in assignments:
            self._attach(
                sentence,
                frame,
                assignment,
                pack,
                predicate_head=predicate_head,
                predicate_type=predicate_type,
                style=style,
                locale=locale,
                depth=depth,
            )

        # A copular locative ("John is in Paris") makes the complement the syntactic
        # head, so it is not among the predicate's dependents and has to be assigned
        # a role explicitly. Without this the WHERE slot would silently stay empty.
        if complement is not None:
            complement_assignment = self.semantic_roles.assign(
                sentence,
                predicate_head,
                complement,
                predicate_type,
                deprel_override=complement_deprel,
            )
            if complement_assignment is not None:
                self._attach(
                    sentence,
                    frame,
                    complement_assignment,
                    pack,
                    predicate_head=predicate_head,
                    predicate_type=predicate_type,
                    style=style,
                    locale=locale,
                    depth=depth,
                    extra_exclude=COMPLEMENT_SPAN_EXCLUDE,
                )

        self._attach_clausal_conjuncts(
            sentence, frame, predicate_head, style=style, locale=locale, depth=depth
        )

        # The marker may have been consumed as a `case`/`mark` dependent and so never
        # reached _attach. Check the final word directly, once, at the top level.
        if depth == 0 and frame.dangling_marker is None and sentence.tokens:
            final = sentence.tokens[-1]
            if self._is_dangling_marker(sentence, final, pack):
                frame.dangling_marker = final.lower_lemma

        self._resolve_slot_dependent_sense(frame, pack)
        frame.unresolved_slots = self._unresolved_slots(frame, universal)
        frame.intent = self._detect_intent(sentence, predicate_head, frame)
        return frame

    # -- predicate ---------------------------------------------------------

    def _build_predicate(
        self, sentence: ParsedSentence, head: Token, pack: LanguagePack
    ) -> tuple[Token, Predicate | None, Token | None, str]:
        """Identify the predicate and its type.

        Returns three things:

        * the token whose dependents carry the clause's arguments - not always the
          token the predicate's lemma comes from: in "John is tired" the arguments
          hang off ``tired``, but the predicate is the STATE *tired*;
        * the predicate itself;
        * a *complement* token that still needs a role of its own, which happens
          when a copular complement is the syntactic head ("John is in Paris") or when
          the clause is a bare nominal fragment ("The engineer");
        * the relation to score that complement as, since the root carries ``root``
          rather than a role-bearing relation.
        """
        copula = sentence.child_by_deprel(head.index, "cop")
        expletive = sentence.child_by_deprel(head.index, "expl")

        # "There is a problem" - existence, not a property of "problem".
        if expletive is not None and copula is not None:
            return (
                head,
                Predicate(
                    type=PredicateType.EXISTENCE,
                    lemma=copula.lower_lemma,
                    text=sentence.span_text([copula.index, head.index]),
                    token_index=head.index,
                    token_indices=sorted({copula.index, head.index}),
                    sense="existence",
                ),
                head,
                "nsubj",
            )

        if copula is not None:
            predicate = self._copular_predicate(sentence, head, copula, pack)
            # Only a locative/oblique complement needs its own slot; an adjective or
            # a predicate noun *is* the predicate and must not be duplicated.
            complement = head if predicate.sense == "located" else None
            return head, predicate, complement, "obl"

        # A bare noun phrase is not a predicate. "The engineer" and "Yesterday in
        # Paris," are fragments whose predicate has not been written yet, and typing
        # them as STATE/engineer is both wrong and self-defeating: the frame then looks
        # complete, so the one thing the text is actually waiting for - a predicate -
        # is the one thing that stops being expected.
        #
        # Nominal predication in all three POC languages carries a copula, which the
        # branch above has already handled, so requiring one here is safe.
        if head.upos in {"NOUN", "PROPN", "PRON", "NUM"} and not sentence.has_child_deprel(
            head.index, "cop", "aux"
        ):
            # A temporal noun opening a sentence is a WHEN adjunct, not a subject:
            # "Yesterday in Paris," is waiting for both a subject and a predicate.
            temporal = self._looks_temporal(head, pack)
            return head, None, head, "obl:tmod" if temporal else "nsubj"

        predicate_type = self._predicate_type(sentence, head, pack)
        return (
            head,
            Predicate(
                type=predicate_type,
                lemma=head.lower_lemma,
                text=head.text,
                token_index=head.index,
                token_indices=[head.index],
                sense=self._predicate_sense(sentence, head, pack, predicate_type),
            ),
            None,
            "obl",
        )

    @staticmethod
    def _looks_temporal(token: Token, pack: LanguagePack) -> bool:
        """Whether a noun is a time expression, according to the language pack."""
        lemma = token.lower_lemma
        if lemma in pack.temporal_adverbs:
            return True
        if token.entity_type == "TIME":
            return True
        temporal_classes = {"weekday", "month", "time_unit", "time_adverb",
                            "jour", "mois", "duree", "adverbe_temps",
                            "thu", "thang", "thoi_luong", "trang_tu_thoi_gian"}
        return bool(pack.classes_of_word(lemma) & temporal_classes)

    def _copular_predicate(
        self, sentence: ParsedSentence, head: Token, copula: Token, pack: LanguagePack
    ) -> Predicate:
        """Build the predicate of a copular clause.

        Three readings, distinguished by what the copula's complement is:

        * a prepositional phrase -> STATE / *located*, and the complement becomes a
          LOCATION element rather than the predicate ("John is in Paris");
        * an adjective -> STATE / *property* with the adjective as the lemma
          ("John is tired");
        * a noun -> STATE / *identity* ("John is an engineer").
        """
        has_case = sentence.has_child_deprel(head.index, "case")
        predicate_type = PredicateType.STATE

        # A lemma-driven override can turn a copular clause into a CHANGE
        # ("John became tired"), which the language pack decides.
        typed = pack.predicate_type_for_lemma(copula.lower_lemma)
        if typed in {"CHANGE"}:
            predicate_type = PredicateType(typed)

        if has_case:
            # The complement is a circumstance; the predicate is bare existence at
            # a place. Keep the copula's lemma so the frame stays language-neutral.
            return Predicate(
                type=predicate_type,
                lemma=copula.lower_lemma,
                text=copula.text,
                token_index=copula.index,
                token_indices=[copula.index],
                sense="located",
            )

        sense = "property" if head.upos == "ADJ" else "identity"
        return Predicate(
            type=predicate_type,
            lemma=head.lower_lemma,
            text=head.text,
            token_index=head.index,
            token_indices=sorted({copula.index, head.index}),
            sense=sense,
        )

    def _predicate_type(
        self, sentence: ParsedSentence, head: Token, pack: LanguagePack
    ) -> PredicateType:
        """Classify the predicate (spec section 10), language pack first."""
        for rule in pack.predicate_type_rules:
            if self._rule_matches(sentence, head, rule.get("when", {})):
                try:
                    return PredicateType(rule["type"])
                except (KeyError, ValueError):
                    logger.warning("bad predicate_type_rule in %s pack: %r", pack.language, rule)

        typed = pack.predicate_type_for_lemma(head.lower_lemma)
        if typed:
            try:
                return PredicateType(typed)
            except ValueError:
                logger.warning("unknown predicate type %r in %s pack", typed, pack.language)

        if head.upos in {"NOUN", "PROPN", "ADJ"}:
            return PredicateType.STATE
        return PredicateType.ACTION

    @staticmethod
    def _rule_matches(sentence: ParsedSentence, head: Token, when: dict[str, Any]) -> bool:
        if "has_child_deprel" in when:
            if not sentence.has_child_deprel(head.index, when["has_child_deprel"]):
                return False
        if "lemma_in" in when:
            if head.lower_lemma not in {str(l).lower() for l in when["lemma_in"]}:
                return False
        if "upos_in" in when:
            if head.upos not in set(when["upos_in"]):
                return False
        return True

    #: Sense conditions this code path can evaluate. A rule using anything else is
    #: skipped rather than half-matched - that is what made "know" come out as
    #: `identity` when only the copular branch could have decided that.
    _SENSE_CONDITIONS = frozenset({"type", "lemma_in"})

    def _predicate_sense(
        self,
        sentence: ParsedSentence,
        head: Token,
        pack: LanguagePack,
        predicate_type: PredicateType,
    ) -> str | None:
        """Assign a coarse, cross-language sense where the pack defines one.

        Senses that depend on copular structure or on which slots got filled are
        decided in :meth:`_copular_predicate`, which has that information. Here a
        rule matches only if every one of its conditions is both understood and
        satisfied, and only if at least one condition actually discriminates.
        """
        senses = pack.grammar.get("predicate_senses", {}) or {}
        for name, spec in senses.items():
            when = spec.get("when", {}) or {}
            if not set(when).issubset(self._SENSE_CONDITIONS):
                continue

            wanted_type = when.get("type")
            if wanted_type:
                wanted = {wanted_type} if isinstance(wanted_type, str) else set(wanted_type)
                if predicate_type.value not in wanted:
                    continue

            lemma_in = when.get("lemma_in")
            if lemma_in is None:
                # `type` alone is not discriminating: every STATE would match.
                continue
            if head.lower_lemma not in {str(l).lower() for l in lemma_in}:
                continue

            return name
        return None

    def _resolve_slot_dependent_sense(
        self, frame: UniversalPhraseFrame, pack: LanguagePack
    ) -> None:
        """Assign a predicate sense that depends on which slots got filled.

        Some senses cannot be decided before role assignment. *located* is the clearest
        case, and languages reach it by different routes: English and Vietnamese show it
        in clause structure (a copula with a prepositional complement, or a locative
        verb), while French UD makes `etre` the root verb, so the only evidence is the
        lemma plus the presence of a locative slot.

        Running this after attachment lets one declarative rule per language cover all
        of them. An already-assigned sense is never overwritten.
        """
        if frame.predicate is None or frame.predicate.sense is not None:
            return

        for name, spec in (pack.grammar.get("predicate_senses", {}) or {}).items():
            when = spec.get("when", {}) or {}
            if "has_slot" not in when:
                continue

            wanted_type = when.get("type")
            if wanted_type:
                allowed = (
                    {wanted_type} if isinstance(wanted_type, str) else set(wanted_type)
                )
                if frame.predicate.type.value not in allowed:
                    continue

            lemma_in = when.get("lemma_in")
            if lemma_in and frame.predicate.lemma not in {
                str(lemma).lower() for lemma in lemma_in
            }:
                continue

            slots = when["has_slot"]
            slots = [slots] if isinstance(slots, str) else list(slots)
            if any(frame.is_filled(slot) for slot in slots):
                frame.predicate = frame.predicate.model_copy(update={"sense": name})
                return

    # -- grammatical meaning ----------------------------------------------

    def _apply_grammatical_meaning(
        self,
        sentence: ParsedSentence,
        head: Token,
        pack: LanguagePack,
        frame: UniversalPhraseFrame,
    ) -> None:
        """Read tense, aspect, modality, voice, negation and certainty off the clause."""
        analysis = self.morphology.analyze(head, sentence.language)
        auxiliaries = self._auxiliaries_of(sentence, head, pack)

        tense: str | None = analysis.tense
        aspect: str | None = analysis.aspect
        modality: str | None = None
        certainty: float | None = None

        for aux in auxiliaries:
            spec = pack.auxiliary_spec(aux.lower_lemma)
            if spec.get("tense"):
                tense = spec["tense"]
            if spec.get("modality"):
                modality = spec["modality"]
            if spec.get("aspect"):
                # Some languages mark aspect on the particle itself rather than through
                # an auxiliary-plus-participle construction.
                aspect = spec["aspect"]
            if spec.get("certainty") is not None:
                certainty = float(spec["certainty"])
            if tense is None:
                aux_analysis = self.morphology.analyze(aux, sentence.language)
                tense = aux_analysis.tense

        aspect = self._aspect_from_auxiliaries(sentence, head, pack, auxiliaries) or aspect

        # "be going to <verb>" is a future, not a motion event.
        periphrastic = self._periphrastic_future(sentence, head, pack)
        if periphrastic:
            tense = periphrastic.get("tense", tense)
            modality = periphrastic.get("modality", modality)

        voice = Voice.PASSIVE if self._is_passive(sentence, head, pack) else Voice.ACTIVE
        negation, negation_note = self._negation(sentence, head, pack, analysis)

        certainty = self._certainty(sentence, head, pack, modality, certainty)

        frame.tense = self._enum(Tense, tense)
        frame.aspect = self._enum(Aspect, aspect)
        frame.modality = modality
        frame.voice = voice
        frame.negation = negation
        frame.certainty = certainty
        if negation_note:
            frame.notes.append(negation_note)

    @staticmethod
    def _auxiliaries_of(
        sentence: ParsedSentence, head: Token, pack: LanguagePack
    ) -> list[Token]:
        """Every dependent that carries tense, aspect or modality.

        Found by relation *and* by the language pack's auxiliary list, because the two
        disagree across languages: English auxiliaries are labelled ``aux``, while
        Vietnamese preverbal particles are tagged ADV/``advmod``. Relying on the label
        alone would leave Vietnamese with no tense at all.
        """
        found: dict[int, Token] = {
            token.index: token
            for token in sentence.children_by_deprel(head.index, "aux", "aux:pass", "cop")
        }
        for child in sentence.children(head.index):
            if child.index in found:
                continue
            if pack.auxiliary_spec(child.lower_lemma) and child.base_deprel in {
                "advmod",
                "dep",
                "discourse",
                "compound",
            }:
                found[child.index] = child
        return [found[index] for index in sorted(found)]

    @staticmethod
    def _enum(enum_cls: type, value: str | None) -> Any:
        if value is None:
            return None
        try:
            return enum_cls(value)
        except ValueError:
            logger.debug("value %r is not a %s", value, enum_cls.__name__)
            return None

    def _aspect_from_auxiliaries(
        self,
        sentence: ParsedSentence,
        head: Token,
        pack: LanguagePack,
        auxiliaries: list[Token],
    ) -> str | None:
        """Derive aspect from the auxiliary chain plus the main verb's form."""
        lemmas = {aux.lower_lemma for aux in auxiliaries}
        head_form = head.feat("VerbForm")
        head_tense = head.feat("Tense")

        rules = pack.grammar.get("aspect_rules", []) or []
        # Most specific first: perfect progressive needs both auxiliaries.
        for rule in sorted(rules, key=lambda r: -len(r.get("aux_lemmas", []) or [])):
            required = set(rule.get("aux_lemmas") or ([rule["aux_lemma"]] if rule.get("aux_lemma") else []))
            if not required or not required.issubset(lemmas):
                continue
            if rule.get("verbform") and head_form != rule["verbform"]:
                continue
            if rule.get("tense_feat") and head_tense != rule["tense_feat"]:
                continue
            return str(rule["aspect"])
        return None

    @staticmethod
    def _periphrastic_future(
        sentence: ParsedSentence, head: Token, pack: LanguagePack
    ) -> dict[str, Any] | None:
        for rule in pack.grammar.get("periphrastic_future", []) or []:
            if head.lower_lemma != str(rule.get("verb_lemma", "")).lower():
                continue
            aux = sentence.child_by_deprel(head.index, "aux", "cop")
            if aux is None or aux.lower_lemma != str(rule.get("aux_lemma", "")).lower():
                continue
            marker = rule.get("marker")
            if marker:
                complement = sentence.child_by_deprel(head.index, "xcomp", "ccomp", "advcl")
                if complement is None:
                    continue
                mark = sentence.child_by_deprel(complement.index, "mark")
                if mark is None or mark.lower_lemma != str(marker).lower():
                    continue
            return dict(rule)
        return None

    @staticmethod
    def _is_passive(sentence: ParsedSentence, head: Token, pack: LanguagePack) -> bool:
        passive_deprels = pack.passive_deprels or {"nsubj:pass", "aux:pass", "csubj:pass"}
        if any(child.deprel in passive_deprels for child in sentence.children(head.index)):
            return True
        return head.feat("Voice") == "Pass"

    @staticmethod
    def _negation(
        sentence: ParsedSentence, head: Token, pack: LanguagePack, analysis: Morphology
    ) -> tuple[bool, str | None]:
        """Detect clause-level negation, keeping constituent negation separate."""
        if analysis.is_negative:
            return True, None

        particles = pack.negation_particles
        for child in sentence.children(head.index):
            if child.lower_lemma in particles and child.base_deprel in {"advmod", "aux", "dep"}:
                return True, None
            if child.feat("Polarity") == "Neg" and child.base_deprel == "advmod":
                return True, None

        # "John met no one" negates an argument, not the event. Recorded as a note
        # so the difference is visible instead of silently collapsed.
        for _, dependent in ((c.index, c) for c in sentence.children(head.index)):
            determiner = sentence.child_by_deprel(dependent.index, "det")
            if determiner is not None and determiner.lower_lemma in particles:
                return True, f"negation scopes over the constituent {dependent.text!r}"
        return False, None

    @staticmethod
    def _certainty(
        sentence: ParsedSentence,
        head: Token,
        pack: LanguagePack,
        modality: str | None,
        from_auxiliary: float | None,
    ) -> float | None:
        """Blend modal certainty with any explicit certainty adverb."""
        adverbs = pack.certainty_adverbs
        for child in sentence.children(head.index):
            if child.base_deprel == "advmod" and child.lower_lemma in adverbs:
                return adverbs[child.lower_lemma]
        if from_auxiliary is not None:
            return from_auxiliary
        if modality is None:
            return None
        return None

    # -- element attachment ------------------------------------------------

    def _attach(
        self,
        sentence: ParsedSentence,
        frame: UniversalPhraseFrame,
        assignment: RoleAssignment,
        pack: LanguagePack,
        *,
        predicate_head: Token,
        predicate_type: str | None,
        style: str | None,
        locale: str | None,
        depth: int,
        extra_exclude: frozenset[str] = frozenset(),
    ) -> None:
        """Turn a role assignment into a frame element in the right slot."""
        role = assignment.role
        if role is None:
            return

        slot = self.universal.slot_for_role(role)
        if slot is None or slot not in ELEMENT_SLOTS:
            logger.debug("role %r maps to no element slot; dropping", role)
            return

        token = sentence.token(assignment.token_index)
        if token is None:
            return

        # A stranded marker ("... Sarah in") is not a filled slot. Treating it as one
        # would be actively harmful: the slot predictor would then see WHERE as
        # already answered and penalise the very slot the marker points to.
        if self._is_dangling_marker(sentence, token, pack):
            frame.dangling_marker = token.lower_lemma
            self._reattach_orphans(
                sentence,
                frame,
                token,
                pack,
                predicate_head=predicate_head,
                predicate_type=predicate_type,
                style=style,
                locale=locale,
                depth=depth,
            )
            return

        # "using Terraform" -> the element is Terraform, not the participle.
        promoted_index = assignment.annotations.get("promote_to")
        span_token = sentence.token(promoted_index) if promoted_index else token
        span_token = span_token or token

        nested_frame: UniversalPhraseFrame | None = None
        if assignment.is_nested and promoted_index is None and depth < MAX_DEPTH:
            nested_frame = self._build_frame(
                sentence,
                token,
                style=style,
                locale=locale,
                depth=depth + 1,
                relation_to_parent=role,
            )

        text = self._element_text(
            sentence,
            span_token,
            nested=nested_frame is not None,
            extra_exclude=extra_exclude,
        )
        analysis = self.morphology.analyze(span_token, sentence.language)

        element = FrameElement(
            text=text,
            head_lemma=span_token.lower_lemma,
            semantic_role=role,
            confidence=assignment.confidence,
            entity_type=span_token.entity_type or token.entity_type,
            token_indices=sentence.subtree_indices(span_token.index),
            features=analysis.filled(),
            annotations={
                key: value
                for key, value in assignment.annotations.items()
                if key != "promote_to"
            },
            alternatives=[
                RoleAlternative(role=h.role, probability=h.probability)
                for h in assignment.alternatives[:3]
            ],
            deprel=assignment.deprel,
            frame=nested_frame,
        )

        if not text:
            # Nothing was said: the constituent was all markers and determiners.
            return

        definiteness = self._definiteness(sentence, span_token, pack)
        if definiteness:
            element.features.setdefault("definiteness", definiteness)

        frame.add(slot, element)

    @staticmethod
    def _is_dangling_marker(
        sentence: ParsedSentence, token: Token, pack: LanguagePack
    ) -> bool:
        """Whether a dependent is a trailing marker awaiting its complement.

        Three conditions: it is the final word, the language pack knows it as an
        adposition, subordinator or adposition-like clause head, and it is not the
        clause's root (so a genuine predicate complement - "the meeting is over" -
        is not mistaken for a stranded preposition).

        Part of speech is deliberately not consulted: parsers tag a stranded
        "because" inconsistently, whereas "it is last and awaits a complement" is
        reliable. Nor is "has no dependents" required - on a fragment a parser may
        hang the preceding adverbial under the marker, which is handled by
        re-attaching those orphans rather than by rejecting the marker.
        """
        if not sentence.tokens or token.index != sentence.tokens[-1].index:
            return False
        if token.is_root:
            return False

        if (
            bool(pack.adposition_cue(token.lower_lemma))
            or bool(pack.subordinator_cue(token.lower_lemma))
            or token.lower_lemma in (pack.syntax.get("clause_head_cues", {}) or {})
        ):
            return True

        # A trailing determiner, coordinator or copula is the same situation: a
        # constituent has been opened and not finished. Recording "the" as a filled WHAT
        # slot is worse than useless - it tells the slot predictor the object has been
        # stated, so the object becomes the one thing it stops expecting. A trailing
        # copula ("The day after Monday is ___") is waiting for its complement, which in
        # SPLM's terms is the predicate itself.
        return token.upos in {"DET", "CCONJ", "AUX"} or pack.function_word_pos(
            token.lower_lemma
        ) in {"DET", "CCONJ", "AUX"}

    def _reattach_orphans(
        self,
        sentence: ParsedSentence,
        frame: UniversalPhraseFrame,
        marker: Token,
        pack: LanguagePack,
        *,
        predicate_head: Token,
        predicate_type: str | None,
        style: str | None,
        locale: str | None,
        depth: int,
    ) -> None:
        """Re-home content a parser hung under a stranded marker.

        On "... to AWS yesterday using", the parser attaches *yesterday* beneath
        *using*. Dropping the marker must not drop the time expression with it, so
        its content dependents are re-assigned against the real predicate.
        """
        for child in sentence.children(marker.index):
            if child.base_deprel in {"punct", "case", "mark", "cc", "det", "cop", "aux"}:
                continue
            assignment = self.semantic_roles.assign(
                sentence, predicate_head, child, predicate_type
            )
            if assignment is None:
                continue
            self._attach(
                sentence,
                frame,
                assignment,
                pack,
                predicate_head=predicate_head,
                predicate_type=predicate_type,
                style=style,
                locale=locale,
                depth=depth,
            )

    def _element_text(
        self,
        sentence: ParsedSentence,
        token: Token,
        *,
        nested: bool,
        extra_exclude: frozenset[str] = frozenset(),
    ) -> str:
        """Surface text of a constituent, minus the machinery that marked its role.

        Markers (``in``, ``to``, ``the``) are evidence, not content: the frame
        records WHERE = "Paris", and the fact that English used *in* to say so is
        already captured by the role itself.
        """
        exclude = set(SPAN_EXCLUDE) | set(extra_exclude)
        if not nested:
            exclude |= self.universal.nested_deprels
        text = sentence.subtree_text(token.index, exclude=exclude)
        return text.strip(" ,.;:")

    @staticmethod
    def _definiteness(
        sentence: ParsedSentence, token: Token, pack: LanguagePack
    ) -> str | None:
        determiner = sentence.child_by_deprel(token.index, "det")
        if determiner is None:
            return None
        feature = determiner.feat("Definite")
        mapping = pack.value_map.get("definiteness", {})
        if feature:
            return str(mapping.get(feature, feature)).lower()
        return None

    def _attach_clausal_conjuncts(
        self,
        sentence: ParsedSentence,
        frame: UniversalPhraseFrame,
        head: Token,
        *,
        style: str | None,
        locale: str | None,
        depth: int,
    ) -> None:
        """Coordinated clauses become sibling frames, not elements.

        "John met Sarah and left early" is two events, and flattening them would
        lose the second predicate entirely.
        """
        if depth >= MAX_DEPTH:
            return
        for conjunct in sentence.children_by_deprel(head.index, "conj"):
            if conjunct.upos not in {"VERB", "AUX"} and not sentence.has_child_deprel(
                conjunct.index, "nsubj", "nsubj:pass", "cop"
            ):
                continue
            frame.children.append(
                self._build_frame(
                    sentence,
                    conjunct,
                    style=style,
                    locale=locale,
                    depth=depth + 1,
                    relation_to_parent="COORDINATE",
                )
            )

    # -- gaps --------------------------------------------------------------

    def _unresolved_slots(
        self, frame: UniversalPhraseFrame, universal: UniversalPack
    ) -> list[str]:
        """Slots this predicate plausibly takes that the text has not filled.

        This is what the ExpectedSlotPredictor turns into a prediction. It is a
        statement about what is *missing*, not about what is required - an English
        sentence is complete without a WHERE.
        """
        if frame.predicate is None:
            return []
        expected = universal.phrase_schema.get("expected_slots_by_predicate_type", {}) or {}
        candidates = expected.get(frame.predicate.type.value, [])
        return [slot for slot in candidates if not frame.is_filled(slot)]

    @staticmethod
    def _detect_intent(
        sentence: ParsedSentence, head: Token, frame: UniversalPhraseFrame
    ) -> str | None:
        """Statement / question / command, from punctuation and mood."""
        if sentence.text.rstrip().endswith("?"):
            return "question"
        if head.feat("Mood") == "Imp":
            return "command"
        if head.upos == "VERB" and not sentence.has_child_deprel(
            head.index, "nsubj", "nsubj:pass", "csubj", "expl"
        ):
            # A finite verb with no subject at all is typically an imperative.
            if head.feat("VerbForm") in {None, "Fin"}:
                return "command"
        return "statement"

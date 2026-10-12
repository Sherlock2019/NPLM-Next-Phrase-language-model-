"""Language pack loading (spec section 13).

A *language pack* is a directory of YAML files holding everything SPLM knows
about one language's surface machinery: grammar, syntax cues, morphology, styles
and idioms. The ``universal`` pack holds the language-independent layer that
every language maps onto.

Adding a language means adding a directory here and listing it in
``config/app.yaml`` - no change to the core engine (spec section 4).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

UNIVERSAL_DIR = "universal"
LANGUAGE_FILES = ("grammar", "syntax", "morphology", "styles", "idioms", "semantics")
UNIVERSAL_FILES = ("phrase_schema", "semantic_roles", "dependency_mapping")


class _StrictLoader(yaml.SafeLoader):
    """A YAML loader that refuses to silently drop a duplicated key.

    All of SPLM's linguistic knowledge lives in these files, and standard YAML
    resolves a repeated key by keeping the last one without complaint. In a table of
    per-verb argument structures that means an entry can vanish and the only symptom
    is a slightly wrong role somewhere downstream. Better to fail loudly.
    """


def _no_duplicate_keys(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False):
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found a duplicate key {key!r}; one of the two entries would be "
                "silently discarded",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys
)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.load(handle, Loader=_StrictLoader) or {}


@dataclass(frozen=True)
class UniversalPack:
    """The language-independent layer shared by every language."""

    phrase_schema: dict[str, Any] = field(default_factory=dict)
    semantic_roles: dict[str, Any] = field(default_factory=dict)
    dependency_mapping: dict[str, Any] = field(default_factory=dict)

    # -- semantic roles ----------------------------------------------------

    @property
    def roles(self) -> dict[str, Any]:
        return self.semantic_roles.get("roles", {})

    @property
    def role_names(self) -> list[str]:
        return list(self.roles.keys())

    def slot_for_role(self, role: str) -> str | None:
        """Which UniversalPhraseFrame field a role fills."""
        return self.roles.get(role, {}).get("slot")

    def question_for_role(self, role: str) -> str:
        return self.roles.get(role, {}).get("question", role)

    def roles_for_slot(self, slot: str) -> list[str]:
        return [name for name, spec in self.roles.items() if spec.get("slot") == slot]

    @property
    def predictable_slots(self) -> list[str]:
        return list(self.semantic_roles.get("predictable_slots", []))

    def normalize_entity_type(self, label: str | None) -> str | None:
        """Map an NER label onto SPLM's entity-type inventory."""
        if not label:
            return None
        aliases = self.semantic_roles.get("entity_type_aliases", {})
        return aliases.get(label.upper(), "OTHER")

    def entity_role_boost(self, entity_type: str | None) -> dict[str, float]:
        if not entity_type:
            return {}
        spec = self.semantic_roles.get("entity_types", {}).get(entity_type, {})
        return {k: float(v) for k, v in (spec.get("roles_boost") or {}).items()}

    def entity_is_animate(self, entity_type: str | None) -> bool | None:
        if not entity_type:
            return None
        spec = self.semantic_roles.get("entity_types", {}).get(entity_type)
        return None if spec is None else bool(spec.get("animate"))

    # -- dependency mapping ------------------------------------------------

    @property
    def floor(self) -> float:
        return float(self.dependency_mapping.get("floor", 0.02))

    def has_exact_prior(self, deprel: str) -> bool:
        """Whether a relation has its own prior rather than inheriting its base's.

        ``obl:agent`` does; plain ``obl`` is what it would otherwise fall back to. The
        difference matters because a subtyped relation is usually far less ambiguous
        than its base, so generic per-predicate knowledge must not override it.
        """
        return deprel in (self.dependency_mapping.get("deprel_priors", {}) or {})

    def deprel_spec(self, deprel: str) -> dict[str, Any]:
        """Prior spec for a relation, falling back from ``obl:tmod`` to ``obl``."""
        priors = self.dependency_mapping.get("deprel_priors", {})
        if deprel in priors:
            return priors[deprel]
        base = deprel.split(":")[0]
        return priors.get(base, {})

    def deprel_prior(self, deprel: str, predicate_type: str | None) -> dict[str, float]:
        """Role distribution for a relation, specialised by predicate type."""
        spec = self.deprel_spec(deprel)
        if predicate_type:
            by_type = spec.get("by_predicate_type", {})
            if predicate_type in by_type:
                return {k: float(v) for k, v in by_type[predicate_type].items()}
        return {k: float(v) for k, v in (spec.get("default") or {}).items()}

    def is_modifier_deprel(self, deprel: str) -> bool:
        return bool(self.deprel_spec(deprel).get("modifier", False))

    def inherits_from_head(self, deprel: str) -> bool:
        return bool(self.deprel_spec(deprel).get("inherit_from_head", False))

    @property
    def nested_deprels(self) -> set[str]:
        return set(self.dependency_mapping.get("nested_deprels", []))

    @property
    def clause_level_deprels(self) -> set[str]:
        return set(self.dependency_mapping.get("clause_level_deprels", []))

    @property
    def functional_deprels(self) -> dict[str, str]:
        return dict(self.dependency_mapping.get("functional_deprels", {}))

    # -- phrase schema -----------------------------------------------------

    @property
    def slot_order(self) -> list[str]:
        return list(self.phrase_schema.get("slot_order", []))

    @property
    def slots(self) -> dict[str, Any]:
        return self.phrase_schema.get("slots", {})

    def question_for_slot(self, slot: str) -> str:
        return self.slots.get(slot, {}).get("question", slot.upper())

    @property
    def predicate_types(self) -> dict[str, Any]:
        return self.phrase_schema.get("predicate_types", {})

    def modality_certainty(self, modality: str | None) -> float | None:
        table = self.phrase_schema.get("modality_certainty", {})
        if modality is None:
            return table.get("none")
        value = table.get(modality)
        return None if value is None else float(value)


@dataclass(frozen=True)
class LanguagePack:
    """Everything SPLM knows about one language's surface realisation."""

    language: str
    grammar: dict[str, Any] = field(default_factory=dict)
    syntax: dict[str, Any] = field(default_factory=dict)
    morphology: dict[str, Any] = field(default_factory=dict)
    styles: dict[str, Any] = field(default_factory=dict)
    idioms: dict[str, Any] = field(default_factory=dict)
    semantics: dict[str, Any] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not any((self.grammar, self.syntax, self.morphology, self.styles))

    # -- slot compatibility ------------------------------------------------

    @property
    def semantics_coverage(self) -> str:
        """How complete this pack's slot-compatibility data is: seed/partial/full.

        Surfaced next to every metric derived from it, so nobody reads a Semantic
        Focus number without knowing how thin the underlying gazetteer is.
        """
        return str(self.semantics.get("coverage", "seed"))

    def slot_requirements(self, slot: str) -> dict[str, Any]:
        return dict((self.semantics.get("slot_requirements", {}) or {}).get(slot, {}))

    def semantic_class_members_for(self, class_name: str) -> set[str]:
        """Members of a class, looked up in semantics.yaml then syntax.yaml."""
        for source in (self.semantics, self.syntax):
            members = (source.get("semantic_classes", {}) or {}).get(class_name)
            if members:
                return {str(m).lower() for m in members}
        return set()

    def classes_of_word(self, word: str) -> set[str]:
        """Every semantic class a word belongs to, across both files."""
        lowered = word.lower()
        found: set[str] = set()
        for source in (self.semantics, self.syntax):
            for name, members in (source.get("semantic_classes", {}) or {}).items():
                if lowered in {str(m).lower() for m in members}:
                    found.add(name)
        return found

    @property
    def semantics_scoring(self) -> dict[str, Any]:
        return dict(self.semantics.get("scoring", {}) or {})

    # -- syntax cues -------------------------------------------------------

    def adposition_cue(self, lemma: str | None) -> dict[str, float]:
        """Role likelihoods contributed by an adposition such as ``in`` or ``by``."""
        if not lemma:
            return {}
        table = self.syntax.get("adposition_cues", {})
        cue = table.get(lemma.lower())
        return {k: float(v) for k, v in cue.items()} if cue else {}

    def fixed_adposition_cue(self, phrase: str | None) -> dict[str, float]:
        if not phrase:
            return {}
        table = self.syntax.get("fixed_adpositions", {})
        cue = table.get(phrase.lower())
        return {k: float(v) for k, v in cue.items()} if cue else {}

    def subordinator_cue(self, lemma: str | None) -> dict[str, float]:
        """Role likelihoods contributed by a subordinator such as ``if`` or ``to``."""
        if not lemma:
            return {}
        table = self.syntax.get("subordinator_cues", {})
        cue = table.get(lemma.lower())
        return {k: float(v) for k, v in cue.items()} if cue else {}

    def semantic_class_members(self, class_name: str) -> set[str]:
        members = self.syntax.get("semantic_classes", {}).get(class_name, [])
        return {str(m).lower() for m in members}

    def semantic_classes_of(self, lemma: str | None) -> set[str]:
        """Which language-pack semantic classes a lemma belongs to."""
        if not lemma:
            return set()
        lowered = lemma.lower()
        return {
            name
            for name, members in (self.syntax.get("semantic_classes", {}) or {}).items()
            if lowered in {str(m).lower() for m in members}
        }

    @property
    def lexical_overrides(self) -> list[dict[str, Any]]:
        return list(self.syntax.get("lexical_overrides", []))

    @property
    def temporal_adverbs(self) -> set[str]:
        return {w.lower() for w in self.syntax.get("temporal_adverbs", [])}

    @property
    def locative_adverbs(self) -> set[str]:
        return {w.lower() for w in self.syntax.get("locative_adverbs", [])}

    @property
    def manner_adverbs(self) -> set[str]:
        return {w.lower() for w in self.syntax.get("manner_adverbs", [])}

    @property
    def slot_sequence_priors(self) -> dict[str, dict[str, float]]:
        raw = self.syntax.get("slot_sequence_priors", {}) or {}
        return {
            state: {slot: float(p) for slot, p in dist.items()}
            for state, dist in raw.items()
        }

    @property
    def dangling_marker_weight(self) -> float:
        return float(self.syntax.get("dangling_marker_weight", 6.0))

    # -- grammar -----------------------------------------------------------

    def predicate_type_for_lemma(self, lemma: str | None) -> str | None:
        if not lemma:
            return None
        lowered = lemma.lower()
        for ptype, lemmas in (self.grammar.get("predicate_types", {}) or {}).items():
            if lowered in {str(item).lower() for item in lemmas}:
                return ptype
        return None

    @property
    def predicate_type_rules(self) -> list[dict[str, Any]]:
        return list(self.grammar.get("predicate_type_rules", []))

    def auxiliary_spec(self, lemma: str | None) -> dict[str, Any]:
        if not lemma:
            return {}
        return dict((self.grammar.get("auxiliaries", {}) or {}).get(lemma.lower(), {}))

    @property
    def negation_particles(self) -> set[str]:
        neg = self.grammar.get("negation", {}) or {}
        return {str(p).lower() for p in neg.get("particles", [])}

    @property
    def certainty_adverbs(self) -> dict[str, float]:
        raw = self.grammar.get("certainty_adverbs", {}) or {}
        return {k.lower(): float(v) for k, v in raw.items()}

    @property
    def passive_deprels(self) -> set[str]:
        markers = self.grammar.get("passive_markers", {}) or {}
        return set(markers.get("deprels", []))

    def constituent_openers(self, slot: str) -> set[str]:
        table = self.grammar.get("constituent_openers", {}) or {}
        return set(table.get(slot, []))

    def function_word_pos(self, word: str | None) -> str | None:
        """Part of speech of a closed-class word, or ``None`` if not one."""
        if not word:
            return None
        lowered = word.lower()
        for pos, members in (self.grammar.get("function_words", {}) or {}).items():
            if lowered in {str(m).lower() for m in members}:
                return str(pos)
        return None

    # -- morphology --------------------------------------------------------

    @property
    def feature_map(self) -> dict[str, str]:
        return dict(self.morphology.get("feature_map", {}) or {})

    @property
    def value_map(self) -> dict[str, dict[str, Any]]:
        return dict(self.morphology.get("value_map", {}) or {})

    def pronoun_features(self, form: str | None) -> dict[str, Any]:
        if not form:
            return {}
        return dict((self.morphology.get("pronouns", {}) or {}).get(form.lower(), {}))

    @property
    def pronouns(self) -> dict[str, dict[str, Any]]:
        return dict(self.morphology.get("pronouns", {}) or {})

    def verb_form(self, lemma: str, form: str) -> str | None:
        table = (self.morphology.get("verb_forms", {}) or {}).get(lemma.lower())
        if not table:
            return None
        value = table.get(form)
        return None if value is None else str(value)

    # -- style / idioms ----------------------------------------------------

    @property
    def style_names(self) -> list[str]:
        return list((self.styles.get("styles", {}) or {}).keys())

    @property
    def default_style(self) -> str:
        return str(self.styles.get("default_style", "casual"))

    def style_spec(self, style: str) -> dict[str, Any]:
        return dict((self.styles.get("styles", {}) or {}).get(style, {}))

    @property
    def idiom_entries(self) -> list[dict[str, Any]]:
        return list(self.idioms.get("idioms", []) or [])

    @property
    def light_verbs(self) -> set[str]:
        return {str(v).lower() for v in (self.idioms.get("light_verbs", []) or [])}

    @property
    def light_verb_nouns(self) -> dict[str, str]:
        raw = self.idioms.get("light_verb_nouns", {}) or {}
        return {k.lower(): str(v) for k, v in raw.items()}


class LanguagePackRegistry:
    """Loads and caches language packs from a directory."""

    def __init__(self, packs_dir: Path) -> None:
        self.packs_dir = Path(packs_dir)
        self._universal: UniversalPack | None = None
        self._packs: dict[str, LanguagePack] = {}

    def universal(self) -> UniversalPack:
        if self._universal is None:
            base = self.packs_dir / UNIVERSAL_DIR
            self._universal = UniversalPack(
                **{name: _load_yaml(base / f"{name}.yaml") for name in UNIVERSAL_FILES}
            )
            if not self._universal.roles:
                logger.warning("universal pack at %s has no semantic roles", base)
        return self._universal

    def get(self, language: str) -> LanguagePack:
        """Return the pack for ``language``, or an empty pack if none exists."""
        code = language.lower()
        if code not in self._packs:
            base = self.packs_dir / code
            if not base.is_dir():
                logger.warning(
                    "no language pack for %r in %s; using an empty pack",
                    code,
                    self.packs_dir,
                )
            self._packs[code] = LanguagePack(
                language=code,
                **{name: _load_yaml(base / f"{name}.yaml") for name in LANGUAGE_FILES},
            )
        return self._packs[code]

    def available(self) -> list[str]:
        """Language codes that have a pack directory on disk."""
        if not self.packs_dir.is_dir():
            return []
        return sorted(
            child.name
            for child in self.packs_dir.iterdir()
            if child.is_dir() and child.name != UNIVERSAL_DIR
        )


@lru_cache(maxsize=4)
def get_registry(packs_dir: Path | str | None = None) -> LanguagePackRegistry:
    """Cached registry. With no argument, uses the configured packs directory."""
    if packs_dir is None:
        from splm.config import get_config

        packs_dir = get_config().language_packs_dir
    return LanguagePackRegistry(Path(packs_dir))

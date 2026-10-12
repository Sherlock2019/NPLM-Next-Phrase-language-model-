"""Per-prediction advantage metrics.

These answer the question the project actually cares about: not "did SPLM pick
Paris?" but "did SPLM recognise that a LOCATION was wanted, concentrate probability
on location-compatible candidates, and raise the correct answer's rank?"

Three rules are enforced by the data model itself, not left to the UI:

1. **Filtering is distinguished from down-ranking.** Re-scoring the top-K does not
   remove anything, so every funnel stage carries a ``hard`` flag. Only stages that
   genuinely restrict the output space are marked hard.
2. **Coverage is always reported.** The slot-compatibility classifier runs on seed
   gazetteers, so any metric derived from it reports how many candidates it could
   actually judge. "No evidence" is never counted as "incompatible".
3. **Nothing is computed from a single hand-picked example and called a result.**
   These are per-prediction observations; aggregation and significance live in
   :mod:`splm.evaluation.metrics`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from splm.model.word_tracker import LexicalStatus
from splm.phrase.slot_predictor import OTHER, SlotPrediction

if TYPE_CHECKING:
    from splm.model.candidate_scorer import CandidateScore

#: A candidate needs at least this compatibility with a slot to count as fitting it.
COMPATIBLE_THRESHOLD = 0.6
#: Below this it is counted as a poor fit - "less compatible", never "impossible".
INCOMPATIBLE_THRESHOLD = 0.35


class FunnelStage(BaseModel):
    """One stage of the next-word search funnel (metrics brief sections 2, 19)."""

    name: str
    count: int
    #: True only when the stage genuinely restricts what can be produced.
    hard: bool
    label: str = Field(description="`filtered` for hard stages, `scored / down-ranked` otherwise")
    note: str = ""

    @property
    def is_filter(self) -> bool:
        return self.hard


class SearchSpace(BaseModel):
    """How much of the vocabulary SPLM actually reasoned over."""

    vocabulary_size: int
    candidates_considered: int
    stages: list[FunnelStage] = Field(default_factory=list)

    @property
    def hard_reduction(self) -> float:
        """Genuine reduction in the output space, from vocabulary to considered set.

        This is the only reduction figure that may be called a reduction: everything
        after top-K retrieval re-scores candidates without removing them.
        """
        if self.vocabulary_size <= 0:
            return 0.0
        return 1.0 - (self.candidates_considered / self.vocabulary_size)

    @property
    def hard_reduction_percent(self) -> float:
        return round(self.hard_reduction * 100, 2)

    def downranked_stages(self) -> list[FunnelStage]:
        return [stage for stage in self.stages if not stage.hard]


class SemanticFocus(BaseModel):
    """Probability mass on candidates compatible with the expected slot.

    The headline claim SPLM makes is that it moves probability toward the right *kind*
    of meaning. This measures exactly that, before and after re-scoring.
    """

    slot: str
    base_mass: float
    splm_mass: float
    #: Candidates the compatibility classifier could judge at all.
    evaluated: int
    total: int
    compatible_count: int
    coverage_note: str = ""

    @property
    def delta(self) -> float:
        return self.splm_mass - self.base_mass

    @property
    def delta_percentage_points(self) -> float:
        return round(self.delta * 100, 2)

    @property
    def coverage(self) -> float:
        return (self.evaluated / self.total) if self.total else 0.0

    @property
    def is_reportable(self) -> bool:
        """Whether enough candidates were judged for the figure to mean anything."""
        return self.total > 0 and self.coverage >= 0.5


class CandidateRelevance(BaseModel):
    """How many of the top candidates fit the expected slot (metrics brief section 8)."""

    slot: str
    top_k: int
    base_compatible: int
    splm_compatible: int
    base_incompatible: int
    splm_incompatible: int
    evaluated: int

    @property
    def base_ratio(self) -> float:
        return self.base_compatible / self.top_k if self.top_k else 0.0

    @property
    def splm_ratio(self) -> float:
        return self.splm_compatible / self.top_k if self.top_k else 0.0

    @property
    def base_noise(self) -> float:
        """Share of the top-K that fits the expected slot poorly."""
        return self.base_incompatible / self.top_k if self.top_k else 0.0

    @property
    def splm_noise(self) -> float:
        return self.splm_incompatible / self.top_k if self.top_k else 0.0


class TargetOutcome(BaseModel):
    """Where a known correct answer ended up (metrics brief sections 10, 12)."""

    target: str
    found: bool
    base_rank: int | None = None
    splm_rank: int | None = None
    base_probability: float | None = None
    splm_probability: float | None = None
    boost_logits: float | None = None
    matched_token: str | None = None

    @property
    def rank_improvement(self) -> int | None:
        if self.base_rank is None or self.splm_rank is None:
            return None
        return self.base_rank - self.splm_rank

    @property
    def base_reciprocal_rank(self) -> float:
        return 1.0 / self.base_rank if self.base_rank else 0.0

    @property
    def splm_reciprocal_rank(self) -> float:
        return 1.0 / self.splm_rank if self.splm_rank else 0.0

    @property
    def verdict(self) -> str:
        """win / loss / tie, by the rank of the correct answer."""
        improvement = self.rank_improvement
        if improvement is None:
            return "not_found"
        if improvement > 0:
            return "win"
        if improvement < 0:
            return "loss"
        return "tie"


class MassByCategory(BaseModel):
    """Probability mass grouped by the slot each candidate best fits.

    Drives the stacked comparison in metrics brief section 23.
    """

    base: dict[str, float] = Field(default_factory=dict)
    splm: dict[str, float] = Field(default_factory=dict)
    unclassified_base: float = 0.0
    unclassified_splm: float = 0.0


def _is_evaluated(score: "CandidateScore", slot: str) -> bool:
    """Whether the compatibility classifier had evidence for this candidate/slot."""
    features = score.features
    if features is None:
        return False
    return bool(features.informative.get("semantic")) and slot in features.slot_compatibility


def _compatibility(score: "CandidateScore", slot: str) -> float | None:
    features = score.features
    if features is None:
        return None
    return features.slot_compatibility.get(slot)


def compute_semantic_focus(
    scores: list["CandidateScore"], slots: SlotPrediction
) -> SemanticFocus | None:
    """Probability mass on slot-compatible candidates, base versus SPLM.

    Base probabilities are renormalised over the candidate set so both columns are
    distributions over the same candidates.
    """
    slot = slots.top_slot
    if slot == OTHER or not scores:
        return None

    base_total = sum(score.base_probability for score in scores) or 1.0
    splm_total = sum(score.splm_probability for score in scores) or 1.0

    base_mass = 0.0
    splm_mass = 0.0
    evaluated = 0
    compatible = 0

    for score in scores:
        if not _is_evaluated(score, slot):
            continue
        evaluated += 1
        compatibility = _compatibility(score, slot) or 0.0
        if compatibility >= COMPATIBLE_THRESHOLD:
            compatible += 1
            base_mass += score.base_probability / base_total
            splm_mass += score.splm_probability / splm_total

    note = ""
    if evaluated < len(scores):
        note = (
            f"{len(scores) - evaluated} of {len(scores)} candidates could not be "
            "classified; the gazetteer is a seed, so absence is not evidence"
        )

    return SemanticFocus(
        slot=slot,
        base_mass=round(base_mass, 4),
        splm_mass=round(splm_mass, 4),
        evaluated=evaluated,
        total=len(scores),
        compatible_count=compatible,
        coverage_note=note,
    )


def compute_relevance(
    scores: list["CandidateScore"], slots: SlotPrediction, top_k: int = 10
) -> CandidateRelevance | None:
    """Compatible-candidate counts in each system's own top-K."""
    slot = slots.top_slot
    if slot == OTHER or not scores:
        return None

    by_base = sorted(scores, key=lambda s: s.base_rank)[:top_k]
    by_splm = sorted(scores, key=lambda s: s.splm_rank)[:top_k]

    def counts(subset: list["CandidateScore"]) -> tuple[int, int, int]:
        compatible = incompatible = evaluated = 0
        for score in subset:
            if not _is_evaluated(score, slot):
                continue
            evaluated += 1
            value = _compatibility(score, slot) or 0.0
            if value >= COMPATIBLE_THRESHOLD:
                compatible += 1
            elif value <= INCOMPATIBLE_THRESHOLD:
                incompatible += 1
        return compatible, incompatible, evaluated

    base_compatible, base_incompatible, base_evaluated = counts(by_base)
    splm_compatible, splm_incompatible, splm_evaluated = counts(by_splm)

    return CandidateRelevance(
        slot=slot,
        top_k=min(top_k, len(scores)),
        base_compatible=base_compatible,
        splm_compatible=splm_compatible,
        base_incompatible=base_incompatible,
        splm_incompatible=splm_incompatible,
        evaluated=max(base_evaluated, splm_evaluated),
    )


def compute_search_space(
    scores: list["CandidateScore"], slots: SlotPrediction, vocabulary_size: int
) -> SearchSpace:
    """Build the search funnel, labelling each stage honestly.

    Only the first step is a real filter: SPLM re-scores the top-K, and a token
    outside it cannot become the argmax. Every later stage *scores* candidates; none
    removes them, so none may be presented as a reduction.
    """
    considered = len(scores)
    slot = slots.top_slot

    stages: list[FunnelStage] = [
        FunnelStage(
            name="model vocabulary",
            count=vocabulary_size,
            hard=False,
            label="available",
            note="every token the base model can emit",
        ),
        FunnelStage(
            name="candidates retrieved",
            count=considered,
            hard=True,
            label="filtered",
            note=(
                "top-K retrieval; tokens outside this set keep their original logits "
                "and so cannot win, making this a genuine restriction"
            ),
        ),
    ]

    lexical_ok = sum(
        1
        for score in scores
        if score.features is not None
        and score.features.lexical_status
        not in {LexicalStatus.NOT_A_PREFIX.value}
    )
    stages.append(
        FunnelStage(
            name="lexically plausible",
            count=lexical_ok,
            hard=False,
            label="scored / down-ranked",
            note="tokens that could extend toward a known word; unknown counts as plausible",
        )
    )

    syntax_ok = sum(
        1
        for score in scores
        if score.features is not None
        and (not score.features.informative.get("syntax") or score.features.syntax >= 0.5)
    )
    stages.append(
        FunnelStage(
            name="syntactically compatible",
            count=syntax_ok,
            hard=False,
            label="scored / down-ranked",
            note="no hard grammar rule is applied; poor fits are lowered, not removed",
        )
    )

    if slot != OTHER:
        slot_ok = sum(
            1
            for score in scores
            if (_compatibility(score, slot) or 0.0) >= COMPATIBLE_THRESHOLD
        )
        stages.append(
            FunnelStage(
                name=f"{slot.upper()}-compatible",
                count=slot_ok,
                hard=False,
                label="scored / down-ranked",
                note="compatibility with the expected slot, from seed gazetteers and POS",
            )
        )

    stages.append(
        FunnelStage(
            name="selected",
            count=1,
            hard=True,
            label="filtered",
            note="the argmax of the re-scored distribution",
        )
    )

    return SearchSpace(
        vocabulary_size=vocabulary_size, candidates_considered=considered, stages=stages
    )


def compute_target_outcome(
    scores: list["CandidateScore"], target: str
) -> TargetOutcome:
    """Locate a known correct answer among the candidates.

    Matching is on the candidate's surface word, case-insensitively, because the
    target is a word while candidates are tokens. A target that tokenises into several
    pieces is reported as not found rather than matched on its first piece - a partial
    match would silently overstate performance.
    """
    wanted = target.strip().lower()
    if not wanted:
        return TargetOutcome(target=target, found=False)

    for score in scores:
        if score.word.lower() == wanted:
            return TargetOutcome(
                target=target,
                found=True,
                base_rank=score.base_rank,
                splm_rank=score.splm_rank,
                base_probability=round(score.base_probability, 6),
                splm_probability=round(score.splm_probability, 6),
                boost_logits=score.delta_logit,
                matched_token=score.token,
            )

    return TargetOutcome(target=target, found=False)


def compute_mass_by_category(scores: list["CandidateScore"]) -> MassByCategory:
    """Group probability mass by the slot each candidate best fits."""
    base_total = sum(score.base_probability for score in scores) or 1.0
    splm_total = sum(score.splm_probability for score in scores) or 1.0

    result = MassByCategory()
    for score in scores:
        features = score.features
        slot = features.best_slot if features is not None else None
        base_share = score.base_probability / base_total
        splm_share = score.splm_probability / splm_total

        if slot is None:
            result.unclassified_base += base_share
            result.unclassified_splm += splm_share
            continue

        result.base[slot] = result.base.get(slot, 0.0) + base_share
        result.splm[slot] = result.splm.get(slot, 0.0) + splm_share

    result.base = {k: round(v, 4) for k, v in result.base.items()}
    result.splm = {k: round(v, 4) for k, v in result.splm.items()}
    result.unclassified_base = round(result.unclassified_base, 4)
    result.unclassified_splm = round(result.unclassified_splm, 4)
    return result


def frame_completion(frame: object | None) -> float:
    """Share of a predicate's plausible slots that the text has filled.

    The "phrase completion score" of metrics brief section 14. Uses the same
    expected-slot table the frame builder uses for ``unresolved_slots``, so the two
    numbers are consistent.
    """
    if frame is None or getattr(frame, "predicate", None) is None:
        return 0.0
    filled = [slot for slot in getattr(frame, "filled_slots")() if slot != "predicate"]
    unresolved = list(getattr(frame, "unresolved_slots", []))
    total = len(filled) + len(unresolved)
    return round(len(filled) / total, 4) if total else 0.0

"""Token-versus-word handling (spec section 25).

Language models predict sub-word pieces; SPLM reasons about words, roles and
meanings. The bridge must be careful in one specific way the spec calls out:

    Do NOT consider a token invalid just because that token alone
    is not in the dictionary.

``international`` + ``ization`` is one word. So a candidate is judged on whether it
could *extend toward* a real word, not on whether it is one.
"""

from __future__ import annotations

import logging
from bisect import bisect_left
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Iterator

logger = logging.getLogger(__name__)

#: Word-boundary markers used by common tokenizers (BPE, SentencePiece).
BOUNDARY_MARKERS = ("Ġ", "▁", " ")


class LexicalStatus(str, Enum):
    """What the lexical layer was able to determine about a candidate."""

    COMPLETE_WORD = "complete_word"
    VALID_PREFIX = "valid_prefix"
    CONTINUES_WORD = "continues_word"
    NOT_A_PREFIX = "not_a_prefix"
    PUNCTUATION = "punctuation"
    #: The honest default when no lexicon is available. Must never be penalised.
    UNKNOWN = "unknown"


@dataclass
class LexicalVerdict:
    """The lexical layer's reading of one candidate token."""

    status: LexicalStatus
    word: str = ""
    is_word_start: bool = False
    evidence: list[str] = field(default_factory=list)

    @property
    def is_informative(self) -> bool:
        """Whether a lexicon actually had something to say.

        Metrics that aggregate lexical judgements must report coverage, so an
        uninformative verdict has to be distinguishable from a negative one.
        """
        return self.status is not LexicalStatus.UNKNOWN


class LexicalTrie:
    """A prefix tree over the words of one language.

    Answers the only two questions the candidate scorer needs: is this string a
    word, and could it still become one?
    """

    __slots__ = ("_root", "_size")

    #: Sentinel key marking the end of a word.
    _END = "\x00"

    def __init__(self, words: Iterable[str] | None = None) -> None:
        self._root: dict[str, object] = {}
        self._size = 0
        for word in words or ():
            self.insert(word)

    def __len__(self) -> int:
        return self._size

    def __bool__(self) -> bool:
        return self._size > 0

    def insert(self, word: str) -> None:
        if not word:
            return
        node = self._root
        for char in word.lower():
            node = node.setdefault(char, {})  # type: ignore[assignment]
        if self._END not in node:
            node[self._END] = True
            self._size += 1

    def extend(self, words: Iterable[str]) -> None:
        for word in words:
            self.insert(word)

    def _node(self, prefix: str) -> dict[str, object] | None:
        node = self._root
        for char in prefix.lower():
            nxt = node.get(char)
            if not isinstance(nxt, dict):
                return None
            node = nxt
        return node

    def is_word(self, text: str) -> bool:
        node = self._node(text)
        return bool(node and self._END in node)

    def is_prefix(self, text: str) -> bool:
        """Whether any word in the trie starts with ``text``."""
        return self._node(text) is not None

    def completions(self, prefix: str, limit: int = 10) -> list[str]:
        """Words beginning with ``prefix``, for debugging and the UI."""
        node = self._node(prefix)
        if node is None:
            return []
        found: list[str] = []

        def walk(current: dict[str, object], suffix: str) -> None:
            if len(found) >= limit:
                return
            if self._END in current:
                found.append(prefix.lower() + suffix)
            for char, child in current.items():
                if char == self._END or not isinstance(child, dict):
                    continue
                walk(child, suffix + char)

        walk(node, "")
        return found

    def __iter__(self) -> Iterator[str]:
        yield from self.completions("", limit=self._size)


class LexicalIndex:
    """The questions :class:`LexicalTrie` answers, over a sorted word list.

    A full dictionary is more than a million forms per language. As nested dicts that
    costs gigabytes; as one sorted list it costs tens of megabytes, and a prefix is
    still a single binary search.
    """

    __slots__ = ("_words",)

    def __init__(self, words: list[str]) -> None:
        #: Lowercased, unique and sorted.
        self._words = words

    def __len__(self) -> int:
        return len(self._words)

    def __bool__(self) -> bool:
        return bool(self._words)

    def is_word(self, text: str) -> bool:
        text = text.lower()
        index = bisect_left(self._words, text)
        return index < len(self._words) and self._words[index] == text

    def is_prefix(self, text: str) -> bool:
        """Whether any word in the index starts with ``text``."""
        text = text.lower()
        index = bisect_left(self._words, text)
        return index < len(self._words) and self._words[index].startswith(text)

    def completions(self, prefix: str, limit: int = 10) -> list[str]:
        """Words beginning with ``prefix``, for debugging and the UI."""
        prefix = prefix.lower()
        start = bisect_left(self._words, prefix)
        found: list[str] = []
        for word in self._words[start : start + limit]:
            if not word.startswith(prefix):
                break
            found.append(word)
        return found


class WordCandidateTracker:
    """Tracks the partially generated word and judges candidate tokens against it.

    Stateless with respect to a single prediction (the partial word is derived from
    the prompt), but also usable across a generation loop via :meth:`advance`.
    """

    def __init__(
        self, trie: LexicalTrie | LexicalIndex | None = None, *, language: str = "en"
    ) -> None:
        self.trie = trie or LexicalTrie()
        self.language = language
        self._partial = ""

    # -- state -------------------------------------------------------------

    @property
    def partial_word(self) -> str:
        return self._partial

    def reset(self, text: str = "") -> "WordCandidateTracker":
        """Set the pending partial word from the tail of ``text``."""
        self._partial = self.trailing_word(text)
        return self

    @staticmethod
    def trailing_word(text: str) -> str:
        """The incomplete word at the end of ``text``, if any.

        "John will meet Sarah in" ends on a complete word followed by nothing, so
        there is no partial; "John will meet Sarah interna" has "interna" pending.
        """
        if not text or text[-1].isspace():
            return ""
        tail = text.split()[-1] if text.split() else ""
        # Strip leading punctuation but keep internal hyphens and apostrophes.
        return tail.lstrip("\"'([{").lower()

    def advance(self, token: str) -> str:
        """Apply a chosen token and return the new partial word."""
        if self.is_word_start(token):
            self._partial = self.normalize(token)
        else:
            self._partial += self.normalize(token)
        return self._partial

    # -- token shape -------------------------------------------------------

    @staticmethod
    def is_word_start(token: str) -> bool:
        return token.startswith(BOUNDARY_MARKERS)

    @staticmethod
    def normalize(token: str) -> str:
        """Strip boundary markers and lowercase, leaving the letters themselves."""
        text = token
        for marker in BOUNDARY_MARKERS:
            if text.startswith(marker):
                text = text[len(marker) :]
                break
        return text.strip().lower()

    # -- judgement ---------------------------------------------------------

    def judge(self, token: str, *, partial: str | None = None) -> LexicalVerdict:
        """Assess a candidate token lexically.

        The contract, from spec section 25: an unknown token is *unknown*, never
        invalid. Only a token that demonstrably cannot extend toward any known word
        earns a negative verdict, and even then only when a lexicon exists to say so.
        """
        pending = self._partial if partial is None else partial
        piece = self.normalize(token)
        starts_word = self.is_word_start(token)

        if not piece:
            return LexicalVerdict(
                status=LexicalStatus.PUNCTUATION,
                is_word_start=starts_word,
                evidence=["token carries no letters"],
            )
        if not any(char.isalpha() for char in piece):
            return LexicalVerdict(
                status=LexicalStatus.PUNCTUATION,
                word=piece,
                is_word_start=starts_word,
                evidence=["token is punctuation or digits"],
            )

        if not self.trie:
            # No lexicon built. Say nothing rather than guessing.
            return LexicalVerdict(
                status=LexicalStatus.UNKNOWN,
                word=piece,
                is_word_start=starts_word,
                evidence=["no lexicon available for this language"],
            )

        candidate_word = piece if starts_word or not pending else pending + piece

        if self.trie.is_word(candidate_word):
            return LexicalVerdict(
                status=LexicalStatus.COMPLETE_WORD,
                word=candidate_word,
                is_word_start=starts_word,
                evidence=[f"{candidate_word!r} is in the lexicon"],
            )
        if self.trie.is_prefix(candidate_word):
            status = (
                LexicalStatus.VALID_PREFIX if starts_word else LexicalStatus.CONTINUES_WORD
            )
            completions = self.trie.completions(candidate_word, limit=3)
            return LexicalVerdict(
                status=status,
                word=candidate_word,
                is_word_start=starts_word,
                evidence=[
                    f"{candidate_word!r} can still become "
                    + ", ".join(repr(c) for c in completions)
                    if completions
                    else f"{candidate_word!r} is a known prefix"
                ],
            )

        return LexicalVerdict(
            status=LexicalStatus.NOT_A_PREFIX,
            word=candidate_word,
            is_word_start=starts_word,
            evidence=[f"no lexicon entry starts with {candidate_word!r}"],
        )

    def score(self, verdict: LexicalVerdict, *, neutral: float = 0.5) -> float:
        """Map a verdict to a score in ``[0, 1]``.

        ``UNKNOWN`` returns exactly ``neutral`` so a missing lexicon cannot move any
        candidate's ranking in either direction.
        """
        return {
            LexicalStatus.COMPLETE_WORD: 1.0,
            LexicalStatus.VALID_PREFIX: 0.75,
            LexicalStatus.CONTINUES_WORD: 0.8,
            LexicalStatus.NOT_A_PREFIX: 0.2,
            LexicalStatus.PUNCTUATION: neutral,
            LexicalStatus.UNKNOWN: neutral,
        }[verdict.status]


def build_trie_from_lexicon(
    lexicon: object, language: str, limit: int | None = None
) -> LexicalTrie | LexicalIndex:
    """Populate a trie from a :class:`splm.linguistic.lexicon.Lexicon`.

    Returns an empty trie when the lexicon has nothing for the language, which the
    tracker reads as "unknown" rather than "invalid".
    """
    sorted_words = getattr(lexicon, "sorted_words", None)
    if sorted_words is not None and limit is None:
        index = LexicalIndex(sorted_words(language))
        if index:
            logger.info("lexical index for %s holds %d words", language, len(index))
        return index

    trie = LexicalTrie()
    try:
        words = lexicon.iter_words(language, limit=limit)  # type: ignore[attr-defined]
    except Exception as exc:
        logger.debug("no lexicon words for %s: %s", language, exc)
        return trie
    trie.extend(words)
    logger.info("lexical trie for %s holds %d words", language, len(trie))
    return trie

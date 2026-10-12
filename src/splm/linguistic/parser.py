"""Linguistic parsing (spec section 14).

The rest of SPLM consumes :class:`ParsedSentence`, never a parser's own objects.
Stanza is the first implementation; swapping it for spaCy, Trankit, UDPipe or a
gold treebank reader means writing one class that returns ``ParsedSentence``.
"""

from __future__ import annotations

import logging
from functools import cached_property
from pathlib import Path
from typing import Any, Iterator, Protocol, runtime_checkable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

ROOT_HEAD = 0


class ParserUnavailable(RuntimeError):
    """Raised when no parser model is installed for a language.

    SPLM never downloads resources at runtime (spec section 33), so this points the
    caller at ``scripts/download_resources.py`` instead of silently fetching.
    """


class Token(BaseModel):
    """One syntactic word, in Universal Dependencies terms.

    This is a *word*, not a surface token: French ``du`` becomes two words
    (``de``, ``le``), which is what the dependency tree is defined over.
    """

    index: int = Field(description="1-based position within the sentence")
    text: str
    lemma: str
    upos: str = Field(description="Universal POS tag")
    xpos: str | None = None
    feats: dict[str, str] = Field(default_factory=dict, description="Raw UD features")
    head: int = Field(description="Index of the head word; 0 means root")
    deprel: str
    start_char: int | None = None
    end_char: int | None = None
    ner: str | None = Field(default=None, description="Raw NER label from the parser")
    entity_type: str | None = Field(
        default=None, description="NER label normalised to SPLM's inventory"
    )
    misc: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_root(self) -> bool:
        return self.head == ROOT_HEAD

    @property
    def base_deprel(self) -> str:
        """``obl`` for ``obl:tmod``, ``nsubj`` for ``nsubj:pass``."""
        return self.deprel.split(":")[0]

    @property
    def lower_lemma(self) -> str:
        return (self.lemma or self.text).lower()

    def feat(self, key: str) -> str | None:
        return self.feats.get(key)

    def __str__(self) -> str:
        return f"{self.index}:{self.text}/{self.upos}<-{self.head}:{self.deprel}"


class ParsedSentence(BaseModel):
    """A dependency-parsed sentence, independent of which parser produced it."""

    text: str
    language: str
    tokens: list[Token] = Field(default_factory=list)
    start_char: int | None = None
    end_char: int | None = None
    parser: str = "unknown"

    model_config = {"ignore_types": (cached_property,)}

    # -- indexed views (built once per sentence) ---------------------------

    @cached_property
    def _by_index(self) -> dict[int, Token]:
        return {token.index: token for token in self.tokens}

    @cached_property
    def _children(self) -> dict[int, list[Token]]:
        table: dict[int, list[Token]] = {}
        for token in self.tokens:
            table.setdefault(token.head, []).append(token)
        for bucket in table.values():
            bucket.sort(key=lambda t: t.index)
        return table

    # -- navigation --------------------------------------------------------

    def token(self, index: int) -> Token | None:
        return self._by_index.get(index)

    def children(self, index: int) -> list[Token]:
        """Direct dependents of the word at ``index`` (use 0 for the root slot)."""
        return list(self._children.get(index, []))

    def child_by_deprel(self, index: int, *deprels: str) -> Token | None:
        """First dependent whose relation matches, comparing full then base label."""
        wanted = set(deprels)
        for child in self.children(index):
            if child.deprel in wanted or child.base_deprel in wanted:
                return child
        return None

    def children_by_deprel(self, index: int, *deprels: str) -> list[Token]:
        wanted = set(deprels)
        return [
            child
            for child in self.children(index)
            if child.deprel in wanted or child.base_deprel in wanted
        ]

    def has_child_deprel(self, index: int, *deprels: str) -> bool:
        return self.child_by_deprel(index, *deprels) is not None

    @property
    def roots(self) -> list[Token]:
        return self.children(ROOT_HEAD)

    @property
    def root(self) -> Token | None:
        roots = self.roots
        return roots[0] if roots else None

    def head_of(self, token: Token) -> Token | None:
        return None if token.is_root else self.token(token.head)

    def path_to_root(self, index: int) -> list[Token]:
        """Ancestor chain, nearest head first. Guards against malformed cycles."""
        chain: list[Token] = []
        seen: set[int] = set()
        current = self.token(index)
        while current is not None and not current.is_root:
            if current.index in seen:
                logger.warning("dependency cycle at word %d in %r", current.index, self.text)
                break
            seen.add(current.index)
            parent = self.token(current.head)
            if parent is None:
                break
            chain.append(parent)
            current = parent
        return chain

    # -- spans -------------------------------------------------------------

    def subtree_indices(self, index: int, *, exclude: set[str] | None = None) -> list[int]:
        """Indices of ``index`` and everything beneath it, in surface order.

        ``exclude`` drops whole subtrees by relation, which is how a constituent's
        span is taken without swallowing a nested clause that belongs elsewhere.
        """
        exclude = exclude or set()
        collected: list[int] = []
        stack = [index]
        seen: set[int] = set()
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            collected.append(current)
            for child in self.children(current):
                if child.deprel in exclude or child.base_deprel in exclude:
                    continue
                stack.append(child.index)
        return sorted(collected)

    def span_text(self, indices: list[int] | set[int]) -> str:
        """Reconstruct surface text for a set of word indices.

        Uses original character offsets when the parser supplied them, so spacing
        and punctuation survive; falls back to joining word forms.
        """
        ordered = sorted(indices)
        if not ordered:
            return ""
        tokens = [self._by_index[i] for i in ordered if i in self._by_index]
        if not tokens:
            return ""

        offsets = [(t.start_char, t.end_char) for t in tokens]
        if all(start is not None and end is not None for start, end in offsets):
            start = min(s for s, _ in offsets)
            end = max(e for _, e in offsets)
            base = self.start_char or 0
            # Offsets are document-relative; self.text is the sentence.
            local_start, local_end = start - base, end - base
            if 0 <= local_start < local_end <= len(self.text):
                return self.text[local_start:local_end].strip()
        return " ".join(token.text for token in tokens)

    def subtree_text(self, index: int, *, exclude: set[str] | None = None) -> str:
        return self.span_text(self.subtree_indices(index, exclude=exclude))

    # -- convenience -------------------------------------------------------

    @property
    def words(self) -> list[str]:
        return [token.text for token in self.tokens]

    @property
    def lemmas(self) -> list[str]:
        return [token.lemma for token in self.tokens]

    def __len__(self) -> int:
        return len(self.tokens)

    def __iter__(self) -> Iterator[Token]:  # type: ignore[override]
        return iter(self.tokens)

    def to_conllu(self) -> str:
        """Serialise back to CoNLL-U, for comparison against gold treebanks."""
        lines = [f"# text = {self.text}"]
        for token in self.tokens:
            feats = "|".join(f"{k}={v}" for k, v in sorted(token.feats.items())) or "_"
            lines.append(
                "\t".join(
                    [
                        str(token.index),
                        token.text,
                        token.lemma or "_",
                        token.upos or "_",
                        token.xpos or "_",
                        feats,
                        str(token.head),
                        token.deprel or "_",
                        "_",
                        f"Ner={token.ner}" if token.ner else "_",
                    ]
                )
            )
        return "\n".join(lines) + "\n"


class ParsedDocument(BaseModel):
    """One or more parsed sentences, in order."""

    text: str
    language: str
    sentences: list[ParsedSentence] = Field(default_factory=list)
    parser: str = "unknown"

    @property
    def first(self) -> ParsedSentence | None:
        return self.sentences[0] if self.sentences else None

    def __len__(self) -> int:
        return len(self.sentences)

    def __iter__(self) -> Iterator[ParsedSentence]:  # type: ignore[override]
        return iter(self.sentences)


@runtime_checkable
class LinguisticParser(Protocol):
    """The contract every parser backend satisfies."""

    def parse(self, text: str, language: str) -> ParsedDocument: ...

    def parse_sentence(self, text: str, language: str) -> ParsedSentence | None: ...

    def supports(self, language: str) -> bool: ...

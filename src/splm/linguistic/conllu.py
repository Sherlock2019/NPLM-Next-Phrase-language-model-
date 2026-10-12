"""CoNLL-U reading, producing the same :class:`ParsedSentence` a parser would.

Two uses:

* **Evaluation.** Gold Universal Dependencies treebanks feed the frame builder
  directly, so SPLM's semantic layer can be measured without a parser's errors
  mixed in (spec section 38).
* **Tests.** A hand-written CoNLL-U string is a deterministic, dependency-free
  fixture, which keeps the frame-building tests fast and model-independent.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Iterator

from splm.linguistic.parser import ParsedDocument, ParsedSentence, Token

logger = logging.getLogger(__name__)

EMPTY = "_"


def _parse_feats(raw: str) -> dict[str, str]:
    if raw == EMPTY or not raw:
        return {}
    features: dict[str, str] = {}
    for chunk in raw.split("|"):
        key, _, value = chunk.partition("=")
        if key and value:
            features[key] = value
    return features


def _parse_misc(raw: str) -> dict[str, str]:
    return _parse_feats(raw)


def parse_conllu_sentence(
    block: str, language: str, *, entity_normalizer: object | None = None
) -> ParsedSentence | None:
    """Convert one CoNLL-U sentence block into a :class:`ParsedSentence`."""
    tokens: list[Token] = []
    text: str | None = None
    offset = 0

    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            key, _, value = line[1:].partition("=")
            if key.strip() == "text":
                text = value.strip()
            continue

        fields = line.split("\t")
        if len(fields) < 8:
            logger.debug("skipping malformed CoNLL-U line: %r", line)
            continue

        token_id = fields[0]
        # Skip multi-word token ranges (1-2) and empty nodes (1.1): the dependency
        # tree is defined over syntactic words only.
        if "-" in token_id or "." in token_id:
            continue

        misc = _parse_misc(fields[9]) if len(fields) > 9 else {}
        ner = misc.get("Ner") or misc.get("NER") or misc.get("Entity")
        if ner in {EMPTY, "O"}:
            ner = None

        form = fields[1]
        start, end = offset, offset + len(form)
        offset = end + 1

        entity_type = None
        if ner and entity_normalizer is not None:
            entity_type = entity_normalizer.normalize_entity_type(ner)  # type: ignore[attr-defined]
        elif ner:
            entity_type = ner.upper()

        try:
            head = int(fields[6]) if fields[6] != EMPTY else 0
        except ValueError:
            head = 0

        tokens.append(
            Token(
                index=int(token_id),
                text=form,
                lemma=fields[2] if fields[2] != EMPTY else form,
                upos=fields[3] if fields[3] != EMPTY else "X",
                xpos=None if fields[4] == EMPTY else fields[4],
                feats=_parse_feats(fields[5]),
                head=head,
                deprel=fields[7] if fields[7] != EMPTY else "dep",
                start_char=start,
                end_char=end,
                ner=ner,
                entity_type=entity_type,
                misc=misc,
            )
        )

    if not tokens:
        return None

    surface = text if text is not None else " ".join(t.text for t in tokens)
    return ParsedSentence(
        text=surface,
        language=language,
        tokens=tokens,
        start_char=0,
        end_char=len(surface),
        parser="conllu",
    )


def parse_conllu(
    content: str, language: str, *, entity_normalizer: object | None = None
) -> ParsedDocument:
    """Convert a CoNLL-U string (any number of sentences) into a document."""
    sentences = [
        sentence
        for block in content.split("\n\n")
        if (
            sentence := parse_conllu_sentence(
                block, language, entity_normalizer=entity_normalizer
            )
        )
        is not None
    ]
    text = " ".join(sentence.text for sentence in sentences)
    return ParsedDocument(text=text, language=language, sentences=sentences, parser="conllu")


def iter_conllu_file(
    path: Path | str, language: str, *, entity_normalizer: object | None = None
) -> Iterator[ParsedSentence]:
    """Stream sentences from a ``.conllu`` file without loading it all into memory."""
    buffer: list[str] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                buffer.append(line)
                continue
            if buffer:
                sentence = parse_conllu_sentence(
                    "".join(buffer), language, entity_normalizer=entity_normalizer
                )
                buffer = []
                if sentence is not None:
                    yield sentence
    if buffer:
        sentence = parse_conllu_sentence(
            "".join(buffer), language, entity_normalizer=entity_normalizer
        )
        if sentence is not None:
            yield sentence


class ConlluParser:
    """A :class:`LinguisticParser` over pre-parsed text, keyed by sentence.

    Lets the evaluation harness run the whole SPLM stack on gold trees, isolating
    SPLM's own contribution from parser error.
    """

    name = "conllu"

    def __init__(self, sentences: Iterable[ParsedSentence]) -> None:
        self._by_text: dict[str, ParsedSentence] = {}
        for sentence in sentences:
            self._by_text[sentence.text.strip()] = sentence

    def supports(self, language: str) -> bool:
        return any(s.language == language for s in self._by_text.values())

    def parse(self, text: str, language: str) -> ParsedDocument:
        sentence = self._by_text.get(text.strip())
        sentences = [sentence] if sentence is not None else []
        if sentence is None:
            logger.debug("no gold parse for %r", text)
        return ParsedDocument(
            text=text, language=language, sentences=sentences, parser=self.name
        )

    def parse_sentence(self, text: str, language: str) -> ParsedSentence | None:
        return self._by_text.get(text.strip())

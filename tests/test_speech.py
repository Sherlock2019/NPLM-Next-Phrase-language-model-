"""Speech lab: metrics, audio I/O, Phrase DNA sorting, validation, the pipeline.

Everything except the last test runs without any model: ASR, TTS and the answer
model are replaced by fakes, and frames come from the CoNLL-U fixtures. The last
test (marked ``llm`` and ``slow``) runs the real local Hugging Face checkpoints and
skips when they are not downloaded.
"""

from __future__ import annotations

import base64
import shutil
from types import SimpleNamespace

import numpy as np
import pytest

from splm.speech.asr import AsrResult, Hypothesis
from splm.speech.audio import AudioError, decode_audio, encode_wav, read_wav
from splm.speech.dna import DnaCategory, DnaItem, DnaSort, clarify, sort_frame, DNA_CATEGORIES
from splm.speech.metrics import cer, extract_numbers, normalize, preserved, wer
from splm.speech.validation import core_gaps, validate


# -- metrics ------------------------------------------------------------------

def test_wer_and_cer_known_values():
    assert wer("book a meeting with sarah", "book a meeting with sarah") == 0.0
    assert wer("book a meeting with sarah", "book meeting with sara") == pytest.approx(2 / 5)
    assert wer("Book a meeting!", "book a meeting") == 0.0  # case and punctuation normalised
    assert cer("sarah", "sara") == pytest.approx(1 / 5)
    assert wer("", "") == 0.0 and wer("", "noise") == 1.0


def test_numbers_are_matched_by_value_not_spelling():
    assert extract_numbers("at three and 4", "en") == ["4", "3"]
    assert extract_numbers("à sept heures", "fr") == ["7"]
    assert extract_numbers("lúc bảy giờ", "vi") == ["7"]
    assert preserved(["3"], "tomorrow at three", numbers=True, language="en") == (1, 1)
    assert preserved(["3"], "tomorrow at tree", numbers=True, language="en") == (0, 1)
    # WER does not hide a spelled-out number: that is measured, not normalised away.
    assert wer("at 3", "at three") > 0


def test_entity_preservation_is_whole_word():
    assert preserved(["Sarah", "Paris"], "meet sarah in paris") == (2, 2)
    assert preserved(["Ann"], "meet Anna") == (0, 1)
    assert preserved([], "anything") == (0, 0)


def test_normalize_keeps_vietnamese_diacritics():
    assert normalize("Hà Nội!") == "hà nội"


# -- audio --------------------------------------------------------------------

def test_wav_roundtrip_and_resampling():
    rate = 22050
    tone = 0.5 * np.sin(2 * np.pi * 440 * np.arange(rate) / rate).astype(np.float32)
    data = encode_wav(tone, rate)
    assert data[:4] == b"RIFF"
    back = read_wav(data, sample_rate=16000)
    assert abs(back.size - 16000) <= 1
    assert np.max(np.abs(back)) == pytest.approx(0.5, abs=0.01)


def test_decode_rejects_empty_and_too_long():
    with pytest.raises(AudioError):
        decode_audio(b"")
    long = encode_wav(np.zeros(16000 * 3, dtype=np.float32), 16000)
    with pytest.raises(AudioError):
        decode_audio(long, 16000, max_seconds=2)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_ffmpeg_decodes_non_wav(tmp_path):
    import subprocess

    wav = tmp_path / "a.wav"
    wav.write_bytes(encode_wav(np.zeros(8000, dtype=np.float32), 16000))
    ogg = tmp_path / "a.ogg"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(wav), "-c:a", "libopus", str(ogg)], check=True)
    samples = decode_audio(ogg.read_bytes(), 16000)
    assert abs(samples.size - 8000) < 800


# -- Phrase DNA sort ----------------------------------------------------------

FULL = "John will meet Sarah in Paris tomorrow by train to discuss the contract."


def test_sort_places_every_part_of_the_sentence(frame_for, sentence_for):
    frame = frame_for(FULL)
    sort = sort_frame(frame, sentence_for(FULL))
    assert [c.key for c in sort.categories] == [k for k, _, _ in DNA_CATEGORIES]
    assert sort.texts("who") == ["John"]
    assert sort.texts("action") and sort.predicate_kind == "action"
    assert any("Paris" in t for t in sort.texts("where"))
    assert any("tomorrow" in t for t in sort.texts("when"))
    assert any("train" in t for t in sort.texts("how"))
    assert sort.texts("for_what"), "the purpose clause belongs in FOR WHAT"
    assert sort.tense == "future"
    assert sort.completeness >= 0.6


def test_sort_without_a_frame_marks_everything_unsorted():
    sort = sort_frame(None, text="hmm uh well", language="en")
    assert sort.unsorted == ["hmm", "uh", "well"]
    assert not sort.filled_keys


def _sort(intent: str, **items: list[str]) -> DnaSort:
    categories = []
    for key, label, _ in DNA_CATEGORIES:
        texts = items.get(key, [])
        categories.append(DnaCategory(key=key, label=label,
                                      items=[DnaItem(text=t, slot=key) for t in texts],
                                      missing=key in items.get("missing", [])))
    return DnaSort(text="", language="en", categories=categories, intent=intent,
                   predicate_kind="action" if items.get("action") else None)


def test_clarify_asks_for_a_clock_time_when_only_a_day_is_given():
    sort = _sort("command", action=["Book"], on_what=["a meeting"], with_whom=["Sarah"], when=["tomorrow"])
    question = clarify(sort)
    assert question is not None and question.missing == "when"
    assert question.question == "What time would you like to book a meeting with Sarah?"


def test_clarify_is_silent_for_statements_and_complete_requests():
    assert clarify(_sort("statement", action=["met"], who=["John"])) is None
    assert clarify(_sort("command", action=["Book"], on_what=["a table"], when=["at 7 pm"])) is None


# -- validation ---------------------------------------------------------------

def test_validation_prefers_a_meaningful_near_tie_but_never_overrides_clear_audio():
    sorts = {
        "but are meeting with sarah": _sort("statement"),  # no predicate
        "book a meeting with sarah": _sort("command", action=["book"], on_what=["a meeting"], with_whom=["Sarah"]),
    }
    close = [Hypothesis(text="but are meeting with sarah", score=-0.40, rank=1),
             Hypothesis(text="book a meeting with sarah", score=-0.45, rank=2)]
    result, _ = validate(close, sorts.__getitem__)
    assert result.changed and result.chosen == "book a meeting with sarah"

    far = [close[0], Hypothesis(text="book a meeting with sarah", score=-5.0, rank=2)]
    result, _ = validate(far, sorts.__getitem__, max_acoustic_gap=1.5)
    assert not result.changed and result.chosen_rank == 1


def test_validation_flags_numbers_the_hypotheses_disagree_on():
    hyps = [Hypothesis(text="call at 7", score=-0.3, rank=1),
            Hypothesis(text="call at 11", score=-0.35, rank=2),
            Hypothesis(text="call at 11", score=-0.36, rank=3)]
    result, _ = validate(hyps, lambda t: _sort("command", action=["call"]), language="en")
    assert any("'7'" in w for w in result.warnings)


def test_core_gaps_never_rewards_having_no_predicate():
    assert core_gaps(_sort("statement")) == 3
    assert core_gaps(_sort("command", action=["book"], on_what=["x"])) == 0


# -- pipeline with fakes ------------------------------------------------------

class FakeASR:
    model_id = "fake/whisper"

    def __init__(self, hypotheses):
        self.hypotheses = hypotheses

    def transcribe(self, samples, language=None):
        return AsrResult(hypotheses=self.hypotheses, language=language or "en",
                         language_source="whisper", audio_seconds=samples.size / 16000, latency_ms=10.0)

    def describe(self):
        return {"model_id": self.model_id, "loaded": True}

    def load(self):
        return self


class FakeTTS:
    voices = {"en": "fake/voice"}

    def supports(self, language):
        return language == "en"

    def synthesize(self, text, language):
        audio = np.zeros(1600, dtype=np.float32)
        return audio, SimpleNamespace(sample_rate=16000, audio_seconds=0.1, latency_ms=5.0,
                                      first_chunk_ms=2.0, model_id="fake/voice")

    def describe(self):
        return {"voices": self.voices, "loaded": ["en"]}

    def load(self, language):
        return None


class FakeAnswerEngine:
    def __init__(self):
        self.calls = []
        self.llm = SimpleNamespace(tokenizer=SimpleNamespace(chat_template=None), token_count=lambda t: len(t.split()))

    def generate(self, prompt, *, use_splm, **kwargs):
        self.calls.append(use_splm)
        return " answer from nplm." if use_splm else " answer from base."


@pytest.fixture()
def fake_pipeline(config, frame_for, sentence_for):
    from splm.speech.pipeline import SpeechPipeline

    def analyze(text, language=None, **_):
        try:
            frame, sentence = frame_for(text), sentence_for(text)
        except BaseException:  # not a fixture sentence (pytest.skip is a BaseException)
            frame = sentence = None
        return SimpleNamespace(frame=frame, sentence=sentence, language=language or "en")

    engine = SimpleNamespace(
        pipeline=SimpleNamespace(analyze=analyze, detector=SimpleNamespace(detect=lambda t: SimpleNamespace(language="en"))),
        config=config,
    )
    answer = FakeAnswerEngine()
    hyps = [Hypothesis(text="John met Sarah in Paris yesterday.", score=-0.2, rank=1),
            Hypothesis(text="John met Sarah in Paris.", score=-0.3, rank=2)]
    return SpeechPipeline(config, engine=engine, asr=FakeASR(hyps), tts=FakeTTS(), answer_engine=answer), answer


def test_each_mode_routes_generation_correctly(fake_pipeline):
    pipeline, answer = fake_pipeline
    wav = encode_wav(np.zeros(16000, dtype=np.float32), 16000)
    base = pipeline.run_audio(wav, "base", "en")
    nplm = pipeline.run_audio(wav, "nplm", "en")
    assert answer.calls == [False, True]
    assert base.response_text == "answer from base." and nplm.response_text == "answer from nplm."
    for turn in (base, nplm):
        assert turn.audio_wav_base64 and base64.b64decode(turn.audio_wav_base64)[:4] == b"RIFF"
        for key in ("asr", "analysis", "generation", "tts", "time_to_first_audio", "end_to_end"):
            assert key in turn.timings_ms
        assert turn.rtf["end_to_end"] is not None
        assert turn.dna is not None and turn.dna.texts("who") == ["John"]


def test_compare_shares_one_recognition(fake_pipeline):
    pipeline, answer = fake_pipeline
    wav = encode_wav(np.zeros(16000, dtype=np.float32), 16000)
    result = pipeline.compare(audio=wav, language="en")
    assert result["shared_asr"] is True
    turns = result["turns"]
    assert set(turns) == {"base", "nplm", "nplm_validated"}
    assert turns["base"]["timings_ms"]["asr"] == turns["nplm_validated"]["timings_ms"]["asr"]
    assert turns["nplm_validated"]["validation"] is not None
    assert turns["base"]["validation"] is None


def test_unknown_mode_is_rejected(fake_pipeline):
    pipeline, _ = fake_pipeline
    with pytest.raises(ValueError):
        pipeline.run_text("hello", "turbo", "en")


# -- benchmark summary --------------------------------------------------------

def test_benchmark_refuses_a_verdict_on_few_items():
    from splm.speech.benchmark import SpeechBenchmark

    rows = []
    for i in range(3):
        for mode in ("base", "nplm", "nplm_validated"):
            rows.append({"id": f"x{i}", "language": "en", "mode": mode, "wer": 0.1, "cer": 0.05,
                         "word_errors": 1, "reference_words": 10, "slots_matched": 2, "slots_total": 3,
                         "entities_kept": 1, "entities_total": 1, "numbers_kept": 0, "numbers_total": 0,
                         "response_source": "generation", "validation_changed": False,
                         "generation_ms": 100.0 if mode == "base" else 130.0, "time_to_first_audio_ms": 300.0,
                         "end_to_end_ms": 400.0, "rtf_end_to_end": 1.0, "rtf_asr": 0.2, "peak_rss_mb": 900.0})
    report = SpeechBenchmark.summarise(rows)
    assert report["comparisons"]["transcript"]["entity_preservation"]["verdict"] == "insufficient_data"
    assert report["per_mode"]["base"]["corpus_wer"] == pytest.approx(0.1)
    assert report["comparisons"]["generation"]["generation_ms"]["difference"] == pytest.approx(30.0)


def test_builtin_set_covers_three_languages():
    from splm.speech.benchmark import load_items

    items, source = load_items()
    assert source.startswith("builtin")
    assert {i["language"] for i in items} == {"en", "fr", "vi"}
    assert sum(1 for i in items if i["language"] == "en") >= 20  # enough for a paired verdict


# -- logits processor hook ----------------------------------------------------

def test_analysis_prefix_analyses_only_the_generated_text():
    torch = pytest.importorskip("torch")
    from splm.model.logits_processor import PhraseLanguageLogitsProcessor

    vocabulary = {1: "<sys>", 2: "Hello", 3: " world"}
    tokenizer = SimpleNamespace(decode=lambda ids, skip_special_tokens=True: "".join(vocabulary[int(i)] for i in ids))
    engine = SimpleNamespace(llm=SimpleNamespace(tokenizer=tokenizer))
    processor = PhraseLanguageLogitsProcessor(engine=engine, prompt="<sys>", analysis_prefix="")
    assert processor._current_text(torch.tensor([[1]])) == ""          # first call = prompt only
    assert processor._current_text(torch.tensor([[1, 2, 3]])) == "Hello world"
    legacy = PhraseLanguageLogitsProcessor(engine=engine, prompt="<sys>")
    assert legacy._current_text(torch.tensor([[1, 2]])) == "<sys>Hello"  # default unchanged


# -- real models (opt-in) -----------------------------------------------------

@pytest.mark.llm
@pytest.mark.slow
def test_real_round_trip_speaks_and_hears_english(config):
    """TTS speaks a sentence; Whisper hears it back; the pipeline answers aloud."""
    from splm.speech.asr import AsrUnavailable
    from splm.speech.pipeline import SpeechPipeline
    from splm.speech.tts import TtsUnavailable

    pipeline = SpeechPipeline(config)
    try:
        audio, info = pipeline.tts.synthesize("John will meet Sarah in Paris tomorrow.", "en")
        pipeline.asr.load()
    except (AsrUnavailable, TtsUnavailable, OSError) as exc:
        pytest.skip(f"speech models not available: {exc}")
    turn = pipeline.run_audio(encode_wav(audio, info.sample_rate), "nplm", "en")
    assert cer("John will meet Sarah in Paris tomorrow.", turn.transcript) < 0.5
    assert turn.response_text and turn.audio_wav_base64

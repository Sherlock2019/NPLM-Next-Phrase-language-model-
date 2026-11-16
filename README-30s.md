# NPLM · Next Phrase Language Model, in 30 seconds

**Understand meaning before predicting language.** · [Full README](README.md)

**WHY.** A language model predicts the next token, often a fragment of a word. It has no idea who does
what, to whom, or where.

| Input | LLM prediction | NPLM prediction |
|---|---|---|
| “John will meet Sarah in ___” | `the` 38.3%, `a` 5.4%, `her` 3.3%: fragments, no idea what kind of word is needed | **Expected slot: location 81.6%**; `Paris`, `London`, `Boston` move up |
| The same event in English, French, Vietnamese | Three unrelated token strings | One frame: ACTION meet · WHO John · WITH WHOM Sarah · WHERE Paris (en↔fr 93.3% agreement) |

**WHAT.** A meaning layer on top of an LLM. It turns each sentence into **Universal Phrase DNA** (who does
what, to whom, where, when, why), predicts the next phrase slot, and re-scores the same LLM's candidates. It
is the meaning layer for [ACM](https://github.com/Sherlock2019/ACM) and
[ACMP](https://github.com/Sherlock2019/Butterfly-effect-AImodel). It is a research proof of concept, rule-based
today, and not a new foundation model.

**SO WHAT.** A prediction a plain model cannot make, one structure across languages, every adjustment
explained, and never a worse rank on the suite (2 wins, 9 ties, 0 losses). Built for AI labs, agent builders
and multilingual NLP teams *(target users still to be validated)*.

**HOW.** Stanza parser → semantic roles → Phrase DNA → context graph → slot predictor → candidate scorer.
All linguistic knowledge lives in YAML language packs (en, fr, vi). 154 tests. Not yet shown to improve
next-word prediction on natural text, and it costs about 4× the latency.

**WHAT NOW.**
```bash
git clone git@github.com:Sherlock2019/NPLM-Next-Phrase-language-model-.git && cd NPLM-Next-Phrase-language-model-
./start.sh   # dashboard → http://127.0.0.1:3010   API → http://127.0.0.1:8001
```
Try `python -m splm.cli predict "John will meet Sarah in" --detail`. Investors: [the ask](README.md#my-ask-for-investors) *(amounts are placeholders)*.

**WHAT NEXT.** Evaluate on Universal Dependencies, then train the slot predictor and scorer. This becomes the
front end of a full **Action Prediction Model**, built with AI frontier labs and sold to them. We need engineers:
[profile](https://dzoannguyentran.jobsmatchnow.com/#projects) · [WhatsApp](https://wa.me/84908618075)

---

**Made with love by [DzoanNguyentran@gmail.com](mailto:DzoanNguyentran@gmail.com) · A better World Builder**

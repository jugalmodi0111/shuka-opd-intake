# Catching the dropped "no": a two-witness ASR trick with Saaras v3

"Bukhar nahi hai" — *no fever.* Run that through speech translation and you will, often enough to matter, get back "has fever." The negation evaporates somewhere between the audio and the English. For a chatbot that's a funny screenshot. For an OPD pre-consult note the doctor skims before walking into the room, it's the opposite of what the patient said — and single-pass speech-to-text gives you no way to notice. You get one clean, confident, wrong English sentence with nothing to check it against.

## Why Saaras

I didn't want a second vendor or an alignment model just to get a second opinion. Saaras v3 already gives you two: the same `speech_to_text.transcribe` call takes `mode="translate"` (English out) and `mode="codemix"` (the patient's actual words, code-mixed, script intact). Same model, same audio, two renderings. That's the only reason the whole idea was cheap enough to ship in an afternoon — the "second witness" is just one more call to an endpoint you're already hitting.

## The design decision: two witnesses, then diff the cues

Translate the audio to *read* it; transcribe it in codemix to *verify* it. Run both, pull negation/laterality/number cues from each, and flag every place the two disagree. A `नहीं` in the codemix view with no `no` in the English view is a dropped negation. The bias is deliberate: recall over precision. A false "please confirm with the patient" costs a second; a missed negation costs a misdiagnosis.

```python
from concurrent.futures import ThreadPoolExecutor
from sarvamai import SarvamAI

stt = SarvamAI(api_subscription_key=KEY).speech_to_text

def two_witness(path):
    with ThreadPoolExecutor(2) as ex:                     # both calls run concurrently
        en   = ex.submit(lambda: stt.transcribe(file=open(path,"rb"),
                         model="saaras:v3", mode="translate").transcript)
        orig = ex.submit(lambda: stt.transcribe(file=open(path,"rb"),
                         model="saaras:v3", mode="codemix").transcript)
        en, orig = en.result(), orig.result()

    NEG = ("nahi", "nahin", "नहीं", "no", "not", "never")
    if sum(orig.lower().count(w) for w in NEG) > sum(en.lower().count(w) for w in NEG):
        return f"⚠ negation dropped in translation — heard: {orig!r}  →  got: {en!r}"
    return en
```

The part the docs won't warn you about: the codemix view comes back in **native Devanagari** (`दर्द`), not romanized (`dard`). My first pass at the cue lexicons was all romanized — they passed every mock test and then silently matched *nothing* on live audio, so the verifier looked like it was working while quietly flagging zero drift. Diff the scripts, not your transliteration of them. (The real version keeps both, plus colloquial number words — `dhai din` = 2.5 days, which translation happily rounds to "two.")

## What you could build on this

The diff pattern generalizes past negation:

- **Laterality + number drift** on the same two views — left/right flips and quantity rounding, with one shared comparator.
- **A confirmation read-back**: pipe the structured note into Bulbul v3 and speak it back to the patient in their language *before* the doctor sees it — close the loop in the room.
- **Lexical disambiguation**: feed the codemix view to Sarvam-105B to catch one-word-many-meanings cases (`chakkar` = vertigo | weakness | presyncope) and generate a follow-up that asks about the *sensation*, never naming a diagnosis.

The whole thing — verifier, gap engine, conversational follow-up — is on GitHub: [shuka-opd-intake](https://github.com/jugalmodi0111/shuka-opd-intake). Clone it, run `make demo` (mock mode, no key), and the dropped-negation case is in the fixtures.

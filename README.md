# shuka (शुक)

> शुक — Sanskrit for *parrot*, the faithful narrator. The bird that repeats what it heard, and only what it heard.

**shuka** is an OPD (outpatient department) pre-consult voice intake system for Indic-language patients. A patient speaks their complaint in Hindi/Tamil codemix; shuka produces a **verified, gap-aware, structured intake note** for the doctor — *without inventing facts* and *without leading the patient toward symptoms they never stated*.

The design is built around one discipline: a system that talks to patients about their health must not put words in their mouth. shuka would rather flag a fact as unverified, or ask the patient to describe a sensation in their own words, than guess.

---

## What it does

```
                          ┌─────────────────────────────────────────┐
                          │              patient audio               │
                          │        (Hindi / Tamil codemix)           │
                          └──────────────────┬──────────────────────┘
                                             │
                    ┌────────────────────────┴────────────────────────┐
                    │  Saaras v3 ASR — run TWICE on the same audio     │
                    │  translate  → transcript_en  (English)          │
                    │  transcribe → transcript_original (codemix)     │
                    └───────┬──────────────────────────────┬──────────┘
                            │                              │
              ┌─────────────▼────────────┐    ┌────────────▼─────────────┐
              │  CORE #1: THE VERIFIER   │    │  CORE #2: THE GAP ENGINE │
              │  verify.py               │    │  gaps.py                 │
              │  two-witness drift check │    │  runs on transcript_     │
              │  negation / laterality / │    │  original ONLY           │
              │  number drift            │    │  6 gap kinds + probes    │
              └─────────────┬────────────┘    └────────────┬─────────────┘
                            │                              │
                            └──────────────┬───────────────┘
                                           │
                          ┌────────────────▼─────────────────┐
                          │  structured IntakeNote (schema.py)│
                          │  facts carry provenance +         │
                          │  needs_confirmation               │
                          │  gaps carry non-leading probes    │
                          └───────────────────────────────────┘
```

Optional: a prescription/lab image is read by a vision step (`vision.py`) whose prompts are constrained to a frozen allowlist — it transcribes the document, it does not diagnose.

The note is not a dead end. Each gap is an **answerable follow-up**: the patient (or front-desk staff) answers, the answer is folded back into the note, the gap resolves, and the dialogue accumulates — see [Conversational follow-up](#conversational-follow-up).

---

## Architecture — two cores

### CORE #1 — The Verifier (`src/shuka/verify.py`)

A **two-witness faithfulness check**. Saaras v3 runs twice on the same audio: `translate` mode yields `transcript_en` (English), `transcribe` mode yields `transcript_original` (codemix, preserving the patient's actual words). `cross_check()` extracts cue sets from both views and flags three drift classes:

- **Negation drift** — a `nahi`/`no` present in one view but absent in the other (in either direction: a dropped negation *or* a spurious one added by translation).
- **Laterality drift** — left↔right mismatch via a semantic side-map (`laterality.json`).
- **Number drift** — zero-tolerance value mismatch. Handles Indic colloquial quantities: `dedh`/`derh`=1.5, `dhai`/`adhai`=2.5, `sava`=1.25, and `paune X` = value(X) − 0.25 (`quantities.json`).

`verify_facts()` attaches `needs_confirmation` to drifted facts. Crucially, the verifier is **fail-safe, not fail-open**: when `transcript_original` is `None` (the transcribe call failed), `cross_check()` returns `verified=False` and `verify_facts()` marks **every** safety-critical fact (stated/denied symptoms, HPI duration/onset/location, medication doses) as needing confirmation — rather than trusting a single unwitnessed view (`verify.py:209-213`, `verify.py:281-303`).

### CORE #2 — The Gap Engine (`src/shuka/gaps.py`)

Runs **only on `transcript_original`** — the gaps shuka cares about are visible in the codemix and erased by translation into English. Six gap kinds (`GapKind`, `schema.py:24`):

- **`lexical_collapse`** — one vernacular word spans many clinical referents (`chakkar` → vertigo | presyncope | giddiness | general weakness | orthostatic hypotension). The probe asks the patient to describe the **sensation**, never naming a diagnosis.
- **`temporal_anchor`** — duration anchored to a regional festival ("Holi ke baad se") rather than the clock; resolved against a festival calendar (Holi, Diwali, winter-harvest, Eid, Navratri, Ganesh Chaturthi, Onam; 2024–2027) with alias support (Pongal = Bihu = Lohri = Makar Sankranti = winter_harvest — `festivals.json`).
- **`category_denial`** — echo reduplication ("bukhar-vukhar nahi") denies a fuzzy *category*, not a single symptom.
- **`frequency_drop`** — pro-drop grammar omits a count ("ulti hui" with no number).
- **`register_ambiguity`** — an English biomedical token in a vernacular matrix ("BP", "sugar") is likely doctor-told rather than self-felt; the probe asks which.
- **`hpi_dimension`** — a missing HPI axis (onset / duration / character / location).

---

## The non-leading boundary — the safety invariant

Follow-up questions may **only** ask about complaints the patient already stated. They must **never** propose an unstated symptom. This is enforced in three independent places:

1. **`assert_non_leading()` (`gaps.py:234`)** — a hard blacklist gate. If a follow-up names any term in the symptom/disease blacklist (`symptom_names.json`, 41 terms: bukhar, cancer, palpitations, dhadkan, …) that the patient did **not** themselves utter, it raises `ValueError`. A blacklisted term *is* allowed when it appears in the gap's own `patient_term` — echoing the patient's own word back is faithful, not leading.
2. **`Gap.leads_diagnosis` pydantic field (`schema.py:124`)** — a `field_validator` that hard-fails validation if this is ever set `True`. The flag exists only so the gate can prove it is always zero.
3. **LLM fallback (`llm_probe_unknown_collapse`, `gaps.py:277`)** — for collapse terms absent from the static lexicon, Sarvam-M generates an experiential probe, capped at **3 probes per intake** (`PROBE_CAP = 3`, enforced at the orchestrator level, `gaps.py:225,335`). Every generated probe still passes through `assert_non_leading`.

---

## Conversational follow-up

The intake is a **conversation, not a one-shot**. Each detected gap renders as an answerable question with option chips and a free-text box (`POST /followup`, `src/shuka/followup.py`):

- **Option-chip answers** fold **deterministically** — fast, no model call. The HPI axis is filled, the symptom/medication is confirmed, the gap is marked `resolved`.
- **Free-text answers** are routed through **Sarvam** (`_llm_interpret`) — the model interprets the answer in conversational context (original transcript + running `qa_history` + the field being filled) and returns a **constrained JSON patch** (`field_value` + `additional_findings`). Code applies the patch; the model never rewrites the whole note, so the non-leading boundary and provenance stay enforced in code. Falls back to the deterministic fold if the LLM is unavailable.
- Every turn appends a `QATurn` to `qa_history`, keeping the **verbatim** answer (not the normalized value) so the doctor always sees the patient's own words. Later turns carry the accumulated context.

---

## Mock mode — zero API spend, fully runnable

`INTAKE_MODE=mock` (the default, `config.py:8`) reads every model response from `fixtures/`. A missing fixture raises `FixtureMissingError` (`sarvam.py:24`) — it **never** silently falls through to a live API call. This makes the entire system, including the full test suite and all eval gates, runnable and testable with **no API key and no spend**.

`INTAKE_MODE=live` uses the real **Saaras v3** (ASR — `transcribe` with `mode=translate` for the English witness and `mode=codemix` for the original), **Bulbul v3** (TTS readback), and **Sarvam-105B** (LLM structuring + free-text follow-up interpretation) via the `sarvamai` SDK. Notes on the live path, learned from real calls:

- **Concurrent ASR** — the two Saaras passes run in parallel (`asr.transcribe_both`), cutting ASR wall-clock from ~3–4s to ~1s.
- **Reasoning budget** — Sarvam-105B is a reasoning model; without an explicit `max_tokens` the reasoning trace eats the whole budget and `content` comes back empty. The client caps reasoning and reserves room for the JSON answer; if the primary still returns empty it **falls back to `sarvam-30b`** (`config.llm_model_fallback`).
- **Native-script lexicons** — live Saaras returns Hindi in Devanagari (`दर्द`), not romanized; the gap lexicons carry both romanized **and** native-script (Devanagari/Tamil) keys so detectors fire on live output.
- **Wiring guardrail** — `make wiring` verifies (no network) that every model seam, server route, and UI fetch is wired; `make wiring-live` does one real round-trip per model to catch API-side breakages (deprecated model, invalid speaker) that mocks cannot.

---

## Eval instruments (`eval/`)

| Instrument | Command | Status |
|---|---|---|
| **Corruption gate** — 5 induced-drift cases; verifier must catch 100% of negation/laterality/number drift | `run_eval.py --gates` | **PASS** (5/5) |
| **Gap gate** — benchmark cases assert zero leading follow-ups + vernacular recall of collapse terms | `run_eval.py --gates` | **PASS**, `leading=0` on all cases |
| **Regression gate** — every stated/denied fact must be grounded in the transcript (zero inferred facts) | `run_eval.py --gates` | **PASS** |
| **Grounding audit** (`grounding.py`) — rate of facts anchored to verbatim transcript; emits an HTML report | `run_eval.py --grounding` | reports a rate, does **not** gate |
| **Perturbation generators** (`perturb.py`) — 5 deterministic transcript perturbations (negate, flip laterality, shift duration, drop medication, inject category denial) | imported by tests | n/a (corpus tooling) |
| **Agreement infra** (`agreement.py`) — Cohen's κ between verifier flags and human review for a future real-clip study | requires real clips | infra ready; **no clips collected, κ pending** |

Real clips require manual consent collection — see `eval/realclips/CONSENT.md`. None are collected yet.

---

## Honest residuals

These are real limitations, named plainly.

1. **Correlated omission is the dominant unsolved failure.** When *both* ASR views drop the same utterance (common under real acoustic noise), the verifier cannot catch it — there is no second witness to a sound neither view heard. This is a structural limit of the two-witness design, not a bug. The κ study (`agreement.py`, Task 25) is designed to quantify it but needs real clips that do not yet exist.
2. **Mock-validated, not field-validated.** All gates pass against synthetic/fixture data. No real patient audio has been run through the system. The festival calendar, collapse map, and lexicons are **authored, not learned**.
3. **Eval circularity guard.** Per-case `en_renderings` and gap keywords are authored at case-creation time and pinned — never tuned post-run. But the gap benchmark cases were authored by the same author as the detectors, so high recall on them is **necessary-but-not-sufficient** evidence of correctness.
4. **Lexicon coverage is finite.** The collapse map covers **6 Hindi** (`chakkar`, `gas`, `garmi`, `kamzori`, `dard`, `jhunjhuni`) + **2 Tamil** (`mayakkam`, `soodu`) terms, each with romanized **and** native-script keys so live Saaras output matches. The LLM fallback (cap 3) handles unknowns, but its probes are gated only for *non-leading-ness* — not for broader clinical sensibility. A Hindi/Tamil term outside the lists won't fire a static gap until added.
5. **`register` field pydantic warning.** `Symptom.register` / `Medication.register` (`schema.py:53,83`) shadow a `BaseModel` attribute, emitting a cosmetic `UserWarning` at import. No functional impact.
6. **Free-text follow-up normalization can drift.** Sarvam interpreting a free-text answer occasionally re-phrases it (e.g. `parso` "day-before-yesterday" → "last night"). The **verbatim** answer is always preserved in `qa_history`, so the doctor can audit the original words.

---

## Quickstart

The project uses `uv` (lockfile `uv.lock` committed) and a `Makefile`.

```bash
make install            # uv sync — install deps
make demo               # INTAKE_MODE=mock uv run shuka demo  (no key, no spend)
make test               # pytest tests + all 3 eval gates
make serve              # uvicorn shuka.server:app --reload → http://localhost:8000  (web UI)
make run AUDIO=path [IMAGE=path]   # run the pipeline on a file
make audit              # grounding audit (run_eval.py --grounding)
make wiring             # guardrail: model seams + routes + UI wiring (no network)
make wiring-live        # guardrail + one real round-trip per Sarvam model
make lint               # ruff check src eval tests
```

The web UI (`make serve`, then open `http://localhost:8000`) is a single-file front end: pick a sample or record live, watch a live pipeline stepper while it runs, then see the verified note, drift flags, and answerable follow-up gaps with a running conversation log.

Direct eval commands:

```bash
uv run python eval/run_eval.py --gates                  # corruption + gap + regression gates
uv run python eval/grounding.py --corpus eval/corpus    # grounding audit → HTML report
```

Current state: **95 tests pass**; all 3 gates **PASS**; wiring guardrail **PASS**.

---

## Secrets & config

- **No secrets in the repo.** The API key lives only in a git-ignored `.env`. `.env` is listed in `.gitignore`; `.env.example` is committed as the template.
- **`SARVAM_API_KEY`** is read from the environment only, never committed.
- The default `INTAKE_MODE=mock` means the demo and the full test suite run with **zero API spend and no key required**.

---

## Judging map — claim → evidence

Every file below has been confirmed to exist in the repo.

| Claim | Evidence |
|---|---|
| Verifier catches induced drift | `eval/corruption/*.json` (5 cases) + `eval/run_eval.py` corruption gate → **PASS** |
| Number drift handles Indic quantities (dedh/dhai/paune) | `src/shuka/lexicons/quantities.json` + `verify.py:88-89,166-191` + `eval/corruption/number_dhai_to_two.json` |
| Negation drift in both directions (dropped + spurious) | `verify.py:218-234` + `eval/corruption/negation_drop_fever.json`, `negation_spurious.json` |
| Zero leading follow-ups | `gaps.assert_non_leading` (`gaps.py:234`) + gap gate `leading=0` on all cases |
| `leads_diagnosis` can never be True | `schema.py:124-135` `field_validator` hard-fails on True |
| No inferred facts | regression gate **PASS** + `structure.py` faithfulness contract + `schema.py:57-60` provenance validator |
| Fail-safe on ASR loss | `verify.cross_check` `verified=False` branch (`verify.py:211-213`) → `verify_facts` (`verify.py:281-303`) |
| Gaps detected on codemix, not English | `gaps.detect_gaps` operates on `transcript_original` (`gaps.py:327-345`) |
| Festival temporal anchoring + aliases | `src/shuka/lexicons/festivals.json` (`pongal`=`bihu`=`lohri`=`winter_harvest`) + `gaps.detect_temporal_anchor` |
| LLM probe cap enforced | `gaps.py:225` `PROBE_CAP = 3` + orchestrator break `gaps.py:335` |
| Non-diagnostic vision | `vision.ALLOWED_PROMPTS` frozenset (`vision.py:10`) + import-time asserts (`vision.py:33-35`) + `tests/test_vision.py` allowlist spy (`len == 3`) |
| Mock mode never calls live APIs | `sarvam.FixtureMissingError` (`sarvam.py:24`) + `config.intake_mode = "mock"` default |
| No secrets committed | `.gitignore` contains `.env`; `.env.example` committed as template |
| κ agreement infra exists, clips pending | `eval/agreement.py` `cohen_kappa` + `eval/realclips/CONSENT.md` (no clips) |
| Follow-ups are answerable; free-text → LLM | `src/shuka/followup.py` (`_llm_interpret` + deterministic fold) + `POST /followup` + `tests/test_followup.py` |
| Every model seam + route + UI fetch is wired | `eval/wiring_check.py` (`make wiring` / `make wiring-live`) + `tests/test_wiring.py` |

---

## Source layout

```
src/shuka/
  verify.py     CORE #1 — two-witness drift check
  gaps.py       CORE #2 — gap engine + non-leading gate
  schema.py     IntakeNote / Symptom / Gap pydantic models + validators
  structure.py  transcript → IntakeNote (faithfulness contract)
  vision.py     prescription/lab OCR with frozen prompt allowlist
  merge.py      merge audio facts + document facts
  readback.py   confirmation readback (Bulbul v3 TTS)
  followup.py   conversational loop — fold gap answers back into the note
  pipeline.py   end-to-end orchestration
  sarvam.py     SarvamClient — mock/live seam, 105b + 30b fallback, fixture loading
  asr.py        transcribe_both (translate + transcribe)
  config.py     settings (INTAKE_MODE, SARVAM_API_KEY)
  render.py     note rendering
  cli.py        `shuka` CLI (typer)
  server.py     FastAPI app
  lexicons/     authored JSON: collapse_map, festivals, quantities, …

eval/
  run_eval.py     --gates / --grounding
  perturb.py      deterministic perturbation generators
  grounding.py    grounding-rate audit + HTML report
  agreement.py    Cohen's κ infrastructure
  wiring_check.py model-seam + route + UI guardrail (make wiring[-live])
  corruption/     5 induced-drift gate cases
  gaps/           gap benchmark cases (leading=0, vernacular recall)
  corpus/         grounding corpus
  realclips/      CONSENT.md (no clips yet)

web/index.html    single-file front end (pipeline stepper, gaps, conversation log)

tests/            95 tests across verify, gaps, structure, vision, followup, wiring, …
```

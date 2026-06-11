# Real Clip Consent Protocol

Real audio clips used for the correlated-omission study (Task 25) must not be committed
to this repository. They require explicit patient consent under the following protocol:

## Consent Requirements

1. **Informed consent**: Patient must be told the recording will be used for AI system evaluation.
2. **De-identification**: No name, date of birth, MRN, or facility identifier in the audio.
3. **Anonymized reference**: Use clip IDs (`clip_001`, `clip_002`, ...) not patient names.
4. **Data handling**: Audio stored encrypted at rest; deleted after annotation.
5. **Annotation format**: See `eval/agreement.py` for the required JSON schema.

## Study Design

For each real clip, two independent annotators (one human reviewer + the verifier system)
independently label each mentioned fact as `stated`, `denied`, or `unconfirmed`.

Cohen's κ measures agreement. The dominant failure mode — **correlated omission** — occurs
when both ASR views drop the same utterance. Neither the verifier nor the human reviewer
can catch what was never transcribed. κ is therefore a lower bound on real-world faithfulness.

## Collection Status

| Clips collected | 0 |
|----------------|---|
| Target          | 25 |
| κ computed      | pending |

Clips must be collected manually. The infrastructure in `eval/agreement.py` is ready.

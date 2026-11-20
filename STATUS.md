# Round 2 status

Branch: round2 (not pushed). Untouched: outputs/final, outputs/groq_v1_final, raw_outputs_for_drive.zip.

| Phase | State | Notes |
|---|---|---|
| 1 Rule fixes (no LLM) | done | 5 fixes kept (D27 to D32). Test split not worse. |
| 2 Judge v2, one Groq run | ready, waiting | prompt v2 + rejudge mode + stop guards committed; estimated ~179k tokens; run starts at 05:35 IST |
| 3 Random gold set | labels done | 60 random clips labelled blind: 13 YES -> eval/gold_random.yaml |
| 4 Compare and decide | not started | |

Next: at 05:35 IST run `run.py --provider groq --rejudge-from outputs/groq_v1_final --out outputs/groq_v2` with all fixes OFF, then rescore with fixes ON into outputs/final_v2.

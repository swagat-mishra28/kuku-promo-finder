# Run the listwise rerank stage on Groq (later)

Run this **after 23:40 IST** on 21 Nov 2026, or any time at least 24 hours after the last Groq run. Groq's limit is a rolling 24-hour window of 200,000 tokens; the round-2 run used 122,454 tokens, finishing at 05:56 IST.

## Cost

6 calls (30 clips, batches of 10, 2 passes with different shuffles). The dry run against a fake server sent prompts of 10.9k to 12.7k characters, about 21k input tokens in total. With output and reasoning that is **about 26k tokens**. The largest single call is about 4.5k tokens, under Groq's ~8k tokens-per-minute limit, and calls are spaced 60 s apart. Total time about 6 minutes.

If a 429 appears, the stage stops after that one call, keeps the blend order, and records `stopped_on_error` in run_meta.json. Do not loop.

## Commands (PowerShell, from the project folder)

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONIOENCODING = "utf-8"

# 1. Rerank on plain v1 (same rules as outputs/final). Makes the 6 Groq calls.
python run.py --no-fixes --provider groq --model openai/gpt-oss-120b --rescore-from outputs/groq_v1_final --rerank --out outputs/groq_v3

# 2. Same, with the round-2 rule fixes on, re-using the saved rerank scores. No calls.
python run.py --provider none --rescore-from outputs/groq_v3 --rerank-saved --out outputs/final_v3

# 3. Evaluation tables on gold (odd, even, all) and gold_random, next to v1 and v1 plus fixes.
python eval/compare_runs.py . v1=outputs/final v1+fixes=outputs/r2_v1fix v3=outputs/groq_v3 v3+fixes=outputs/final_v3
```

Check after step 1: `outputs/groq_v3/run_meta.json` should show `"rerank": {"reranked": 30, "calls": 6, ...}` and `rerank_tokens`. Any `problems` listed there are batches where the judge left out a clip or sent bad JSON; those clips were scored neutral.

In step 2, the rule fixes can move a few clips into or out of the top 30. Clips without a saved rerank score keep their blend score; only clips with a saved score are reordered among themselves.

## How to decide

Use the same rule as round 2: adopt the rerank only if the even split does not get worse on recall@15 and precision@15 and the all-episode numbers improve. The gold set has 31 clips, so one clip is about 3 points.

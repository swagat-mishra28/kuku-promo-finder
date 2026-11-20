# Claude Code prompts, in order

Open the `kuku-promo-finder` folder in VS Code, start Claude Code in that folder, and paste these one at a time. Wait for each to finish and read what it reports before moving on. CLAUDE.md already tells Claude Code the project rules, so the prompts stay short.

Budget: about 3 hours total. Prompts 1-3 and 7-9 are must-do. 4-6 are what move you from "works" to "shortlist".

---

## Prompt 1: Set up and verify (10 min)

```
Read CLAUDE.md and README.md, then set this project up on my machine:
1. Create a .venv, activate it, install requirements.txt.
2. Run `python -m promo_finder.parser data/episodes` and show me the table.
3. Run `python run.py --out outputs/rules_only_v1` then `python eval/evaluate.py outputs/rules_only_v1/promos.json`.
4. Tell me recall@15 and precision@15 and list the top 5 promos (segments, hook, cliffhanger).
Do not change any code yet. If something fails, show me the error and fix only that.
```

## Prompt 2: Check the full pack (5 min)

All 50 episodes are already in `data/episodes/` and parse cleanly. Run this only as a sanity check on your machine.

```
All 50 episodes are in data/episodes/.
1. Confirm 50 files, numbered 1-50, none missing.
2. Run the parser check. Flag any episode where: events < 30, dialogue lines < 10, duration < 60 s or > 180 s, or any "Start/End" timestamp that failed to parse (compare count of "Start:" lines in the raw file vs parsed events).
3. If any episode uses a format the parser does not handle, fix parser.py so it handles it, keep the old episodes working, and show me a before/after table.
4. List episode numbers missing from 1-50.
5. Re-run rules-only into outputs/rules_only_50eps and give me the top 15.
```

## Prompt 3: Turn on the free LLM judge (20 min)

Get a free key at https://aistudio.google.com/apikey. Copy `.env.example` to `.env` and paste the key in. (Groq's free tier also works: provider `groq`, model `llama-3.3-70b-versatile`.)

```
I put a Gemini key in .env. 
1. Do a single test call through promo_finder/llm.py with a tiny prompt to confirm the key and model work. If gemini-2.5-flash is not available on my key, list what is and pick the best free flash model.
2. Run `python run.py --provider gemini --out outputs/gemini_v1`. If we hit 429 rate limits, raise llm.min_seconds_between_calls in config.yaml and resume (the cache keeps finished calls).
3. Run the evaluator on it and compare with the rules-only run in a small table: recall@15, precision@15, number of high/medium/low confidence picks, LLM calls, tokens in/out, runtime.
4. Show me 3 promos where rules and LLM disagreed most, with both scores and the LLM's "biggest_weakness". Do not tune anything yet.
```

## Prompt 4: Fix the gold set yourself (30 min, the human-in-the-loop part)

`eval/gold_promos.yaml` is a draft for episodes 1-17. You have to own it, because the interviewers will ask how you know the tool is good.

```
Build me a review sheet so I can label editor picks for ALL episodes quickly:
1. Create eval/review_sheet.md: for every episode, its top 4 distinct moments from outputs/gemini_v1/shortlist_all_scored.json (any rank) plus the episode's final 40 seconds, each with segment timestamps and the transcript.
2. Under each one add an empty line "LABEL: ___  (yes = I'd post it / no / maybe)".
Do NOT fill in labels and do NOT edit eval/gold_promos.yaml. I will do that.
```

After you label: copy your "yes" picks into `eval/gold_promos.yaml` (same format, with the `why` in your own words). Aim for 25-35 promos across 50 episodes. Then:

```
I updated eval/gold_promos.yaml. Re-run the evaluator on outputs/rules_only_50eps and outputs/gemini_v1 with --k 15 and --k 30. Then check "shortlist recall": what share of gold promos appear anywhere in each run's shortlist_all_scored.json. Give me one table. List every MISSED gold promo with your best guess at why the pipeline missed it (look at its rule sub-scores in the shortlist file).
```

## Prompt 5: Tune honestly (25 min)

```
Tune config.yaml against the gold set without overfitting:
1. Split episodes into tune (odd episodes) and test (even episodes). Gold promos follow their episode.
2. Write eval/tune.py: small grid over scoring.weights (hook, cliff, standalone, heat), finale_bonus, ranking.llm_weight (0.4/0.6/0.8). Use cached LLM results only (no new API calls): read shortlist_all_scored.json and recompute blended scores and ranking offline.
3. Pick the best setting on TUNE episodes by recall@15 + precision@15, then report it on TEST episodes next to the current config.
4. Only update config.yaml if test-set numbers improve. Show me the diff and both tables.
```

## Prompt 6: Prove the model is swappable (15 min)

```
Prove model swapping works:
1. Get a second free judge running: Groq (provider groq, model llama-3.3-70b-versatile, key in GROQ key env var) or local Ollama if I have it. Ask me for the key if needed.
2. Run the full pipeline with it into outputs/<provider>_v1 and evaluate.
3. Make a comparison table: Gemini vs the second model vs rules-only (recall, precision, agreement on top-10 overlap, tokens, runtime).
4. Add a "Swap the model in one line" example to README.
```

## Prompt 7: Simulate the interview "new input" (15 min)

```
In the interview they will run this on a show it has never seen. Simulate that:
1. Hold out episodes 41-50 as a "new show": copy them to data/holdout/ and run `python run.py --episodes data/holdout --out outputs/holdout_test` with the tuned config.
2. Also test robustness: make data/stress/ with copies of 2 episodes where you (a) change "Scene heading" lines to upper case, (b) delete the CONTINUITY NOTES line, (c) add Windows line endings and a few blank lines inside blocks. The parser must give identical event counts. Fix it if not.
3. Add tests/test_pipeline.py (pytest) covering: parser counts, no promo outside 20-60 s, no cut through a dialogue line, cold-open hook comes after its body, outputs files exist. Run them.
4. Give me a 5-line checklist for running it live in the interview.
```

## Prompt 8: GitHub + free hosting (20 min)

```
Prepare the public prototype without leaking Kuku's content:
1. git init, check .gitignore covers data/episodes/*.txt, outputs/, .cache/, .env. Run `git status` and show me that no screenplay text or transcript is staged. Also grep the staged files for 3 distinctive lines from the screenplays (e.g. one line of dialogue from Episode 1) to be sure.
2. Commit. Then give me the exact commands to create a public GitHub repo with gh (or the web steps) and push.
3. Make app.py deploy-ready for Streamlit Community Cloud: it must start with no data/episodes folder, ask the user to upload .txt screenplays, and read the API key from the sidebar or st.secrets (never hard-coded). Add a "rules only (free)" default.
4. Write the deploy steps for share.streamlit.io in 6 short lines.
```

## Prompt 9: Raw outputs folder for submission (10 min)

```
Build submission/raw_outputs/ (NOT committed to git):
1. Copy the final full-pack runs unedited: rules-only on all 50 episodes, Gemini on all 50, and the second model if we have it. Each with promos.md, promos.csv, promos.json, shortlist_all_scored.json, eval_report.md, run_meta.json.
2. Add a short INDEX.md: what each folder is, the exact command and config that produced it, and the date.
3. Zip it as submission/raw_outputs.zip. I will upload it to Google Drive as "anyone with the link".
```

## Prompt 10: The 2-page solution doc (30 min)

Edit `SOLUTION_DOC_DRAFT.md` first: put your own decisions and your own "where AI got it wrong" story in it. Then:

```
Turn SOLUTION_DOC_DRAFT.md into a 2-page PDF (submission/solution_doc.pdf):
1. Fill every [[...]] placeholder with real numbers from our final runs and eval reports. If a number does not exist, tell me instead of inventing it.
2. Keep it to 2 A4 pages, 10.5-11 pt body, one small table for results. Cut words, not font size.
3. Plain writing: no hype words, no em-dash chains, no rule-of-three lists, no closing summary paragraph.
4. Generate it with reportlab (or markdown -> HTML -> PDF), open it, and confirm the page count.
```

## Prompt 11: Walkthrough video script (optional, 10 min + recording)

```
Write a 2:45 screen-recording script for me to read in my own voice: 
0:00 the problem in one sentence; 0:15 run `python run.py` live on a new folder; 0:45 open promos.md and read the #1 pick (hook, cliffhanger, why); 1:20 show one honest failure from eval_report.md; 1:50 switch the model in config.yaml and re-run; 2:20 cost and scale in two sentences. 
Mark which window/file to show at each step. Keep sentences short and spoken.
```

## Prompt 12: Interview prep (do the night before)

```
Quiz me on this codebase like a Kuku interviewer. One question at a time, wait for my answer, then tell me what I missed. Cover: why rules first and LLM second, how cut points are chosen, how cold opens work and why the hook must be the payoff, how the ranking order is decided, what the gold set is and its bias, the worst failure mode, cost per show at 50 episodes, what I'd build next with a paid API and video access. 10 questions.
```

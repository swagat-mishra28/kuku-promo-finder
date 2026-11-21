# Promo Finder for microdrama screenplays

Kuku AI Generalist assignment, Problem 1. Reads a show's timestamped screenplays and returns a ranked list of 20-60 second promo clips. Each clip opens on a hook, cuts on a cliffhanger, and should make sense to someone who has never seen the show.

**Live app:** https://kuku-promo-finder-awumukf6sgq3evtbmsljth.streamlit.app/ (try the built-in sample show, or upload your own screenplays; rules-only mode needs no key)

## Run it

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# put screenplays in data/episodes/  (one .txt per episode, any filename with the episode number)

python run.py --provider none                            # rules only: free, offline, about 7 s for 50 episodes
python run.py --provider groq --model openai/gpt-oss-120b   # rules + LLM judge (key in .env)
python eval/evaluate.py outputs/<run>/promos.json --k 5,10,15,25 --covered 1-50
streamlit run app.py                                     # upload a show (.txt files or a .zip) in the browser
```

Run on a new show: `python run.py --episodes path/to/new_show --out outputs/new_show`. Parse problems (bad timing lines, missing headers, gaps in episode numbers) are worked around and printed as warnings, and saved in `run_meta.json`.

Re-rank a finished run without paying for the LLM again: `python run.py --rescore-from outputs/groq_v1_final --out outputs/final_main`. This reuses the saved LLM scores and applies the current `config.yaml`.

## Plug in your own model

Any OpenAI-compatible endpoint works with three lines in `.env`, plus the key (in the web app, pick the provider and paste the key in the sidebar instead):

```
PROMO_LLM_PROVIDER=openai_compatible
PROMO_LLM_MODEL=your-model-name
PROMO_LLM_BASE_URL=https://your-api.example.com/v1
PROMO_LLM_API_KEY=...
```

The same three settings exist under `llm:` in `config.yaml`. Built-in providers: `groq`, `gemini`, `openrouter`, `openai`, `anthropic`, `ollama`, `openai_compatible`. There are no SDKs, only plain HTTP. Answers are cached on disk, keyed by provider, model, reasoning effort and prompt. `tests/test_swap_provider.py` runs the full pipeline against a fake OpenAI-compatible server to show the swap needs no code change.

## How it works

| Step | Who does it | What happens |
|---|---|---|
| 1. Parse | code | Screenplay text becomes timestamped events: camera shots, actions, dialogue (speaker, tone), SFX |
| 2. Generate | code | Every legal cut: starts and ends on shot boundaries, never mid-line, 20-60 s. Plus "cold opens": a 2-6 s flash of the payoff, then the build-up that stops just before it. About 13,250 candidates for 50 episodes |
| 3. Rule score | code | Hook (first 3 s), cliffhanger (last beat), standalone (relationship words, no mid-sentence opens), conflict density, length |
| 4. Dedupe | code | One version per moment; each episode's own ending always makes the shortlist |
| 5. Judge | LLM | Re-scores the shortlist (2.4 per episode) as a cold viewer: it sees only the clip, never the show bible |
| 6. Rank | code | 0.4 rules + 0.6 LLM, then a posting order that favours early episodes and spreads episodes |
| 7. QA | code + human | Hard checks and flags. Anything not "high" confidence goes to an editor |

## Results on the 50-episode pack

Graded against a 31-clip gold set covering all 50 episodes (see SOLUTION_DOC.md for how it was built and its limits).

| Run | recall@5 | recall@10 | recall@15 | recall@25 | precision@15 |
|---|---|---|---|---|---|
| Rules only (current rules) | 2/31 | 5/31 | 7/31 | 10/31 | 7/15 |
| v1: rules + Groq gpt-oss-120b, original rules (baseline, outputs/final) | 4/31 | 6/31 | 10/31 | 12/31 | 10/15 |
| **Main: v1 + five rule fixes (outputs/final_main)** | **3/31** | **8/31** | **10/31** | **12/31** | **10/15** |

The final list has 25 picks for 31 gold clips, so the best possible recall@15 is 48%. One clip is about 3 points, so the difference between v1 and the main result is within noise. The main result was chosen because its top 10 drops a happy ending and adds two strong clips (see SOLUTION_DOC.md). A second, random 13-clip gold set gives the main result 5/13 at recall@15 (v1 also 5/13).

`outputs/final_main` is re-ranked from the saved LLM scores of the full Groq run (20 Nov 2026, 23:11 to 23:37), with no new LLM calls. Its `run_meta.json` records the source run, config hash and tuning notes.

## Outputs (`outputs/<run>/`)

- `promos.md` editor sheet: segments, hook, cliffhanger, why, flags, transcript
- `promos.csv` / `promos.json` same data for spreadsheets or other tools
- `shortlist_all_scored.json` every shortlisted moment with rule and LLM scores (audit trail)
- `run_meta.json` model, counts, tokens, runtime, parse warnings (and for re-ranked runs: source run, config hash, tuning log)

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

34 tests on invented sample screenplays: parser counts, cut rules, cold-open gap rule, evaluation overlap math, QA flags, malformed input, the provider swap, each of the five rule fixes, judge v2 parsing, stop-on-429 and token-budget guards, the optional rerank stage against a fake server, and a regression test that `--provider none` never calls a model.

## Layout

```
promo_finder/parser.py      screenplay -> events, with parse warnings
promo_finder/candidates.py  legal cuts, cold opens
promo_finder/features.py    rule scores, transcripts
promo_finder/llm.py         provider-agnostic JSON completion with disk cache
promo_finder/judge.py       LLM judge prompt
promo_finder/pipeline.py    orchestration, dedupe, ranking, QA, outputs
promo_finder/rescore.py     re-rank saved scores with no LLM calls
promo_finder/rerank.py      optional listwise second stage (off by default, see docs/RUN_STAGE2.md)
promo_finder/learned.py     optional learned re-blend (off: cross-validation showed no gain)
eval/                       gold set, evaluator, review sheet builder
tests/                      pytest suite (invented data only)
config.yaml                 every weight and threshold
```

The screenplays are Kuku's confidential content. `data/episodes/`, `outputs/`, the review sheet and the label working files are git-ignored on purpose.

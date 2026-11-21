# Round 3 report

> Historical report, kept for the record. It describes the project at the end of that round. The main result is now outputs/final_main (v1 LLM scores plus five rule fixes); the final numbers are in README.md and REPORT_FINAL.md.

Branch `round3` (from round2), local commits only. No Groq calls this round. outputs/final, outputs/groq_v1_final and raw_outputs_for_drive.zip were not touched. Tests: 34 passed. Leak scan: no screenplay lines and no forbidden files tracked.

## Status per phase

| Phase | Status | Decision |
|---|---|---|
| 1 Cross-validated re-blend | done | **No gain. Not adopted.** Weights exported to config, switched off. |
| 2 Listwise rerank stage | done (code, tests, dry run) | Not run on Groq yet. Off by default. Commands in RUN_STAGE2.md. |
| 3 Top 10 side by side | done | eval/top10_compare.md (git-ignored: it quotes the screenplays) |

## Phase 1: the cross-validation table

**Setup:**
- **Data:** the 120 saved v1 clips. 33 are positives: they match the 31-clip gold set or one of the 13 random YES clips.
- **Model:** logistic regression with L2 = 1.0, fixed in advance.
- **Features (8):** rules hook, rules cliffhanger, rules standalone, episode ending, LLM overall, LLM cliffhanger, rank within the episode, and LLM overall relative to the episode average.
- **Folds:** 5, grouped by episode, with 10 episodes each.
- **Scoring:** held-out scores were stitched into one ranking, then put through the normal dedupe, top 25 and posting order, and graded by the evaluator.

| Metric | Current blend (0.4 rules + 0.6 LLM) | CV re-blend |
|---|---|---|
| gold recall@10 | 6/31 | 5/31 |
| gold recall@15 | **10/31** | **8/31** |
| gold recall@25 | 12/31 | 14/31 |
| gold precision@15 | **10/15** | **8/15** |
| gold_random recall@10 | 2/13 | 2/13 |
| gold_random recall@15 | 5/13 | 4/13 |
| gold_random recall@25 | 5/13 | 7/13 |
| gold_random precision@15 (labelled picks) | 5/6 | 4/7 |

| Fold | Gold hits in top 15, current | Gold hits in top 15, CV | Average precision current | Average precision CV |
|---|---|---|---|---|
| 1 | 3 | 1 | 0.68 | 0.59 |
| 2 | 2 | 2 | 0.47 | 0.36 |
| 3 | 2 | 0 | 0.71 | 0.69 |
| 4 | 3 | 3 | 0.76 | 0.86 |
| 5 | 0 | 2 | 0.18 | 0.53 |

**Decision: no gain, not adopted.**
- **Fails all three accept conditions:** the rule needed +2 gold clips at recall@15, no loss in precision@15, and a win in at least 3 of 5 folds. The result was -2, precision 8/15 against 10/15, and 1 fold won.
- **Robust:** fold seeds 7 and 11 gave 7/31.
- **Not caused by the circular feature:** removing rank-within-episode (see below) also gave 8/31.

The learned list is better only deeper down (recall@25 14/31 against 12/31). With 33 positives, 8 weights can't be learned reliably, and the hand-set blend is already about as good as this data supports.

**Why rank-within-episode is partly circular:** the round-1 review sheet showed each episode's top 3 clips by this same v1 score, and most gold clips came from that sheet, so this feature predicts gold partly by construction.

**The learned weights in plain words** (trained on all 120 clips, on standardised features):
- A clip ranked higher than the other clips from its own episode is more likely to be a good promo (strongest weight).
- Its LLM overall score relative to its episode's average matters about as much. How a clip compares with its own episode matters more than its raw LLM score, which gets a small negative weight once the relative score is known.
- Being the episode's ending is the next strongest sign.
- Both cliffhanger scores, rules and LLM, help.
- Rules standalone helps a little, and rules hook adds almost nothing once the rest is known.

The weights are saved under `ranking.learned_blend` in config.yaml with `enabled: false` and `accepted_by_cv: false`. With the switch off, output is identical to round 2.

## Phase 2: listwise rerank (built, tested, not run)

**What it does:**
- **Input:** the top 30 distinct clips after blending, sent to the judge in batches of 10. The judge sees transcripts only: no scores and no episode summary.
- **Seeded shuffles:** two passes with different shuffles, so each clip is ranked twice in different company.
- **Blend:** the judge's ordering is averaged into a rank score, then blended 0.7 blend + 0.3 rank.
- **Contained:** only the order inside the top 30 changes.

**Design choices:**
- **No camera lines by default:** with them, one batch would exceed Groq's ~8k tokens-per-minute limit (D50).
- **Stable batches:** clips are batched by identity, not by score, so repeating a run never pays twice for the same batches (F21).
- **Failure handling:** a missing clip or bad JSON scores neutral, and a 429 stops the stage after one call.

**Tests:** 8 new tests against a fake OpenAI-compatible server. They cover parsing, the shuffle seed, bad JSON, a missing clip, unknown or repeated ids, the cache, stopping on a 429, and off-by-default.

**Cost:** a dry run of the exact command on the real 50 episodes against a local fake server made 6 calls. Estimated cost is **about 26k tokens**, with the largest call about 4.5k.

**Decision:** not adopted yet. It can only be judged after the real run.

## Phase 3: top 10 by eye

eval/top10_compare.md puts v1 and v1 plus the round-2 rule fixes side by side, with no scores and no gold marks.
- **Overlap:** they share 8 of 10 picks.
- **Only in v1:** the episode 1 accusation, and the episode 4 walk into the sunlight. The episode 4 clip is the only flagged "ends on a calm / resolved beat" pick in either list.
- **Only in v1 plus fixes:** episode 36 (a prisoner condemned to die after a wedding) and episode 16 (a beaten thug names who paid him).

## What you must run later

After 23:40 IST tonight (Groq's limit is a rolling 24-hour window), follow RUN_STAGE2.md:
1. `python run.py --no-fixes --provider groq --model openai/gpt-oss-120b --rescore-from outputs/groq_v1_final --rerank --out outputs/groq_v3` (6 calls, about 26k tokens, about 6 minutes)
2. `python run.py --provider none --rescore-from outputs/groq_v3 --rerank-saved --out outputs/final_v3` (no calls)
3. `python eval/compare_runs.py . v1=outputs/final v1+fixes=outputs/r2_v1fix v3=outputs/groq_v3 v3+fixes=outputs/final_v3`

Adopt the rerank only if the even split is not worse at recall@15 and precision@15 and the all-episode numbers improve.

## What is left for you

1. Open eval/top10_compare.md and decide which list you would post. If it's the right-hand one, switch the main result to v1 plus fixes (outputs/r2_v1fix), update the numbers in README, SOLUTION_DOC and INTERVIEW_PREP, and rebuild the zip. (15 min)
2. Review the 12 labels in eval/labels_to_review.md, flip any disagreements, and re-run evaluate.py. (20 min)
3. Optionally, run the rerank stage tonight following RUN_STAGE2.md. (10 min)
4. Rewrite SOLUTION_DOC in your own words, fill in [[N labels changed after my review]], and re-export the PDF (2 pages max). (40 min)
5. Merge round2 and round3 into main, push to GitHub, and deploy on Streamlit Cloud following DEPLOY.md. (25 min)
6. Upload raw_outputs_for_drive.zip to Google Drive ("Anyone with the link, Viewer") and check every link in a private window. (10 min)
7. Submit the form: name, roll no 123BM0753, branch, Problem 1, and the links. (5 min)

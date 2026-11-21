# Round 2 report

> Historical report, kept for the record. It describes the project at the end of that round. The main result is now outputs/final_main (v1 LLM scores plus five rule fixes); the final numbers are in README.md and REPORT_FINAL.md.

Branch `round2`, local commits only. outputs/final, outputs/groq_v1_final and raw_outputs_for_drive.zip were not touched.

## Status per phase

| Phase | Status | Result |
|---|---|---|
| 1 Rule fixes (no LLM) | done | 5 fixes kept on the tune split, test split not worse (D27 to D32). One fix had a dead threshold, found and fixed (F16). |
| 2 Judge v2, one Groq run | partial | Prompt v2 written and tested. The run stopped at clip 87 of 120 on Groq's tokens-per-day limit (429). Stopped after the first error, no retries. |
| 3 Random gold set | done | 60 random clips from all 179 moments, labelled blind: 13 YES (eval/gold_random.yaml). |
| 4 Compare and decide | done | v2 not promoted. v1 stays the main result. |
| Tests | done | 25 passed (10 new: one per rule fix, v2 parsing, v2 prompt, v2 QA flag, stop on 429, stop at token budget). |

## Comparison

Counts are found/total for recall and hits/graded for precision. Gold has 31 clips, so one clip moves recall by about 3 points; gold_random has 13, so one clip moves it by about 8 points. For gold_random, precision counts only picks that overlap one of the 60 labelled clips ("labelled"), and recall is end to end: a YES clip that never reached the shortlist is a miss.

| Run | Gold set | R@5 | R@10 | R@15 | R@25 | P@15 |
|---|---|---|---|---|---|---|
| rules only, original rules | gold odd | 1/17 | 4/17 | 4/17 | 4/17 | 4/13 |
| rules only, original rules | gold even | 3/14 | 4/14 | 4/14 | 4/14 | 4/12 |
| rules only, original rules | gold all | 2/31 | 4/31 | 6/31 | 8/31 | 6/15 |
| rules only, original rules | gold_random | 1/13 | 1/13 | 2/13 | 2/13 | 2/4 labelled |
| v1 (outputs/final, main) | gold odd | 3/17 | 6/17 | 7/17 | 7/17 | 7/15 |
| v1 | gold even | 3/14 | 5/14 | 5/14 | 5/14 | 5/9 |
| v1 | gold all | 4/31 | 6/31 | 10/31 | 12/31 | 10/15 |
| v1 | gold_random | 1/13 | 2/13 | 5/13 | 5/13 | 5/6 labelled |
| v1 + fixes (outputs/r2_v1fix) | gold odd | 4/17 | 7/17 | 7/17 | 7/17 | 7/15 |
| v1 + fixes | gold even | 4/14 | 5/14 | 5/14 | 5/14 | 5/9 |
| v1 + fixes | gold all | 3/31 | 8/31 | 10/31 | 12/31 | 10/15 |
| v1 + fixes | gold_random | 1/13 | 3/13 | 5/13 | 6/13 | 5/5 labelled |
| v2 + fixes (outputs/final_v2, 86 of 120 judged) | gold odd | 2/17 | 4/17 | 6/17 | 6/17 | 6/15 |
| v2 + fixes | gold even | 4/14 | 5/14 | 5/14 | 5/14 | 5/8 |
| v2 + fixes | gold all | 4/31 | 5/31 | 8/31 | 11/31 | 8/15 |
| v2 + fixes | gold_random | 1/13 | 2/13 | 3/13 | 5/13 | 3/4 labelled |

Rules only with the fixes, for reference: gold all R@15 7/31 (was 6/31), P@15 7/15 (was 6/15); gold_random R@15 3/13 (was 2/13).

Checks on the partial v2 run:
- **Same result on the 86 clips both judged.** v1+fixes and v2+fixes restricted to the 86 clips judged by both give exactly the numbers above. The 34 clips v2 never reached were v1's lowest ranked, so the stop does not change the verdict.
- **The shortlist is not the bottleneck.** 12 of the 13 random YES clips were in the 120-clip shortlist.

## Decision: keep v1

Rule: promote v2 only if the even split does not get worse on recall@15 and precision@15 AND the all-episode numbers improve.
- **Even split:** recall@15 5/14 for both. Precision@15 is 5/8 for v2 against 5/9 for v1+fixes, so not worse.
- **All episodes:** recall@15 fell from 10/31 to 8/31 and precision@15 from 10/15 to 8/15. That fails the rule.
- **Random gold set:** recall@15 fell from 5/13 to 3/13, which points the same way.

The likely reason: with the episode summary, the judge's average standalone score went from 5.7 to 7.8 and its overall score from 6.5 to 7.8. The spread of overall scores halved (standard deviation 0.77 to 0.43), and it marked 0 of 86 clips as needing context. Knowing the plot, it stopped separating clips (F19).

The Phase 1 fixes stay on in config.yaml. v1 plus fixes is slightly better than v1 (recall@10 8/31 against 6/31, random recall@25 6/13 against 5/13, same recall@15 and precision@15). Per the round's instruction, I left the main files on v1. Switching the main result to outputs/r2_v1fix is your call.

## Tokens used

- **This run:** 86 calls, 98,945 input and 23,509 output tokens (122,454 total), 05:35:30 to 05:56:13 IST.
- **Why it stopped:** Groq's message reported 199,530 tokens already used against the 200,000 limit. The limit is a rolling 24-hour window, not a 05:30 reset, so tokens from the previous night's run still counted (F18).
- **Phase 1 and 3:** no LLM calls.
- **Finishing v2 later (optional):** about 34 calls and roughly 48k tokens. Wait until well after 23:40 IST tonight, when the previous night's run leaves the window, then re-run the same rejudge command into a new folder. The disk cache skips the 86 done clips. Given F19, I would not spend the quota on this.

## What is left for you

1. Review eval/labels_to_review.md (12 labels from round 1) and, if you like, skim eval/random_labels.md. Flip disagreements in the gold yaml files and re-run evaluate.py. (20 min)
2. Decide whether to switch the main result to v1 plus fixes (outputs/r2_v1fix). If yes, update README, SOLUTION_DOC and INTERVIEW_PREP numbers and rebuild the zip. (15 min)
3. Rewrite SOLUTION_DOC in your own words, fill in [[N labels changed after my review]], and re-export the PDF (2 pages). (40 min)
4. Merge or keep the round2 branch, then push to GitHub and deploy on Streamlit Cloud following DEPLOY.md. (25 min)
5. Upload raw_outputs_for_drive.zip to Google Drive, set "Anyone with the link, Viewer", and check every link in a private window. (10 min)
6. Submit the form: name, roll no 123BM0753, branch, Problem 1, and the links. (5 min)

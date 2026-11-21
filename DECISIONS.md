# Decisions log

Every choice made while finishing the project, with the reason. Newest entries are at the bottom of each phase.

## Before the final push (earlier sessions)

**D01. Model for the first LLM run.** gemini-2.5-flash is closed to new users, so I tried gemini-3.8-flash (overloaded, 503) and then used gemini-3.5-flash. It stopped after 23 calls on the free tier's 20 requests per day limit (see F03).

**D02. Switched the judge to Groq openai/gpt-oss-120b.** Groq's free tier allows about 1,000 requests a day against Gemini's 20. One judge call costs about 1,470 tokens, so 120 calls fit under Groq's 200k tokens a day. The run took 23:11 to 23:37 on 20 Nov 2026 and used 133,397 tokens in and 35,550 out.

**D03. reasoning_effort: low for gpt-oss-120b.** Reasoning tokens count against the daily cap. "low" kept a full judge answer at about 323 output tokens. The setting lives in config.yaml and is sent only to groq and openai_compatible providers.

**D04. min_seconds_between_calls raised from 4 to 13.** Groq's free tier allows about 8,000 tokens a minute. At 1,470 tokens a call, 13 seconds between calls keeps the rate near 6,800 tokens a minute.

**D05. reasoning_effort is part of the LLM cache key.** Without it, changing the effort would silently reuse answers made at a different effort. The key only changes when an effort is actually sent, so the Gemini cache stays valid. Side effect: the 120 cached Groq answers no longer match, so any new Groq run would pay for every call again.

**D06. outputs/groq_v1_final is a frozen copy of outputs/groq_v1.** Swagat labels and reports from it. The only later change to it was the QA confidence fields, recomputed from saved scores at Swagat's request (see D07). Ranks, scores, transcripts and run_meta.json are untouched. outputs/groq_v1 keeps the original QA fields.

**D07. New QA confidence rule for LLM-judged clips.** A clip is flagged only if the LLM's confusing_for_new_viewer text is non-empty, its standalone_score is below 5, or rules and LLM disagree by more than qa.disagreement_gap. Clips that break the 20 to 60 second limit or cut mid-line stay "low". Rules-only runs keep the old logic. The threshold and a switch for the confusing-text condition live in config.yaml (qa.min_llm_standalone, qa.flag_on_confusing_text).

**D08. Review sheet design.** Top 3 shortlisted clips per episode plus 2 random extra cuts per episode (seed 7), listed by start time with no scores, so labelling is not anchored by the model. Extras may overlap listed clips when a short episode has no room, but never end on the same beat. 207 clips in total.

## Final push (21 Nov 2026)

**D09. Command-line provider now beats .env.** llm.py reads PROMO_LLM_PROVIDER from the environment before config, and .env sets it to groq. So `run.py --provider none` would still have called Groq. run.py now writes the command-line choice into the environment. I also set PROMO_LLM_PROVIDER=none in every shell command I ran, as a second guard against spending Groq tokens.

**D10. The AI-drafted status of the gold set is disclosed in SOLUTION_DOC.** The instructions asked SOLUTION_DOC to state plainly that the gold labels were AI-drafted. A later change asked for a plain "labels may be changed if needed" comment in gold_promos.yaml instead of a reviewed:false field, and not to mention that comment publicly. I read that as being about the yaml comment only. The SOLUTION_DOC disclosure stays, because a grader comparing numbers against a gold set needs to know who made it.

## Phase A: labels and gold set

**D11. Labelled all 207 clips myself, from transcripts only.** 44 YES, 96 MAYBE, 67 NO. I did not open scores, ranks or LLM text while labelling. The labels are not fully blind: earlier in the session I had seen the old 11-clip gold set, the rules-only top 5 and three rules-vs-LLM disagreements. That is written at the top of eval/labels_draft.md.

**D12. 31 gold clips, one per episode except episode 3.** 30 episodes covered, none from 47 to 50 because I found no YES clip there, and I did not force one. Episode 3 has two because the rescue and the proposal are separate scenes and both are strong.

**D13. Known bias in the gold set.** 29 of 31 gold clips come from the tool's own per-episode top 3, because the review sheet showed 3 tool clips and 2 random extras per episode. The tool can only score a hit on clips it shortlisted, and the gold set is drawn mostly from those, so recall is flattered. Only E24-1 and E42-1 are extras.

**D14. Gold descriptions are paraphrased.** eval/gold_promos.yaml is tracked in git, so its "why" lines describe the scene in my words and quote no dialogue. The old draft quoted dialogue, so eval/gold_promos_old_draft.yaml is git-ignored, as are labels_draft.md and labels_to_review.md.

**D15. gold_promos.yaml carries the comment "labels may be changed if needed".** Per Swagat's instruction, instead of a reviewed:false field.

## Phase B: evaluation and tuning

**D16. The evaluator grades all 50 episodes with --covered 1-50.** Every episode was reviewed. An episode with no gold clip is still labelled ("nothing here is good enough"), so picks from it count as false alarms. Without the flag, the evaluator assumed the gold range 1 to 46.

**D17. Re-ranking from saved scores lives in promo_finder/rescore.py (`run.py --rescore-from`).** It rebuilds the 120 shortlisted clips, recomputes rule scores with the current config and lexicon, keeps the saved LLM scores, and reuses the pipeline's blend, dedupe, ordering and QA. With the config unchanged it reproduces groq_v1_final exactly (same 25 picks and order, same final and rule scores for all 120). It makes no LLM calls and cannot change shortlist membership.

**D18. Tune on odd episodes, test on even.** I looked at per-clip misses for the tune split only, and at the test split only once, for the before and after numbers.

**D19. One tuning change tried, then reverted.** llm_weight 0.6 to 0.7 helped the tune split at k=5 and k=10 and did not help the test split (precision@15 fell from 5/9 to 5/10). By the rule set for this phase, I reverted it. Eight other single changes were tried on tune only and none beat the baseline on recall@15. Everything is listed in config.yaml under tuning_log. The likely reason nothing moves: most tune gold clips sit at ranks 33 to 104 of 120, too far down for small weight changes to lift them into a 25-pick list.

## Phases C to F

**D20. Model swap proven with a fake provider, not a second real one.** .env held only the Groq key. tests/test_swap_provider.py starts a local OpenAI-compatible server that returns canned judge JSON and runs the full pipeline through llm.py's real HTTP code. outputs/swap_test is the same thing on all 50 episodes: 50 calls, because the pipeline always shortlists each episode's final cut, so the shortlist cannot be smaller than the number of episodes.

**D21. Parser reports problems instead of failing silently.** Malformed timing lines, missing headers, numbers taken from file names, duplicate episode numbers, gaps, empty files and byte-order marks all produce a warning with the file and line. Warnings print in the run log and go into run_meta.json as parse_warnings. Re-parsing the real 50 episodes gives 3,727 events and 0 warnings, the same as before.

**D22. outputs/final is re-ranked from groq_v1_final with no active tuning change.** Its numbers equal groq_v1_final because the only tuning change was reverted (D19). run_meta.json records the source run (23:11:13 to 23:37:09 on 20 Nov 2026), its 120 calls and tokens, the config hash and the tuning log.

**D23. Requirements pinned to the versions tested here.** PyYAML 6.0.3, requests 2.34.2, pandas 3.1.1, streamlit 1.67.0. pytest 9.2.0 is in requirements-dev.txt so the cloud app does not install it.

**D24. App changes for Streamlit Cloud.** Upload .txt files or one .zip (macOS junk files skipped), no bundled screenplays, outputs written to the system temp folder, key from Streamlit secrets then .env then the sidebar, default provider "none". The sidebar choice now also beats .env, the same bug as F07.

**D25. Freed C: by purging pip's cache.** 3.9 GB of re-downloadable package files. C: went from 1.4 GB to 5.1 GB free. Nothing else on C: was touched.

**D26. Public repo hygiene.** SOLUTION_DOC_DRAFT.md quotes dialogue, so it is git-ignored (SOLUTION_DOC.md replaces it). One screenplay line in PROMPTS.md, used as an example search string, was replaced with a placeholder. A scan of every tracked file against all dialogue lines of five words or more from the 50 screenplays finds no matches, and no key-like strings.

## Round 2, Phase 1: rule fixes (21 Nov 2026, from 05:10 IST, branch round2)

Each fix comes from a failure in FAILURES.md, is switched in config.yaml, and was tested cumulatively on the tune split (odd episodes) with saved v1 scores. Rule: keep only if tune recall@15 and precision@15 do not get worse and the reason holds.

**D27. (a) Late-window credit, kept.** F11: the cliff score read only the last 6 s, so an explosion 8 s before the cut counted for nothing. Beats 6 to 12 s before the end that match a genre-general list of big beats (explosions, entrances, reveals, crashes, held shots) or the existing physical words now add up to 0.10. Tune: recall@5 3 to 4, recall@10 6 to 7, recall@15 and precision@15 unchanged.

**D28. (b) Episode-depth penalty counted once, kept.** F11: late episodes lost up to 0.29 of standalone in the rules and were also marked down by the LLM's standalone score. When LLM scores exist, the blend now uses the rule score without the depth penalty. Rules-only runs keep it. Tune: unchanged.

**D29. (c) No hook cut for a strong silent action opening, kept.** F13: an opening action beat with heat 0.5 or more (a punch, an explosion) is a hook even without dialogue, so the 25% silent-opening cut no longer applies to it. Tune: unchanged.

**D30. (d) Delivery words in tone tags are not a resolved ending, kept.** F12: "(Soft, Tender)" describes how a line is said, not that the story settled. soft, gentle, tender and warm are stripped from tone tags before the calm-ending check. The same words in action or dialogue text still count. Tune: unchanged. (Round 1 tried removing these words everywhere; this is narrower.)

**D31. (e) Resolved endings rank below open endings, kept.** F14: when the rules flag a calm ending and the LLM rates the cliffhanger below 6, the clip's final score is capped just below the lowest open-ended clip. Two judges agreeing that a clip ends settled is a strong signal. Tune: unchanged.

**D32. Test split checked once after all five.** Even episodes: recall@5 3/14 to 4/14, everything else unchanged (recall@15 5/14, precision@15 5/9). All episodes: recall@10 6/31 to 8/31, recall@5 4/31 to 3/31, recall@15 10/31 and precision@15 10/15 unchanged. Not worse on the test split, so all five stay on. The small movement says the remaining misses are not caused by these rule details.

## Round 2, Phase 2: judge v2

**D33. Judge v1 kept as is; v2 added beside it (llm.judge_version).** v1's prompt is unchanged so earlier runs stay reproducible from the cache. v2 starts with a version tag, so its cache keys never collide with v1.

**D34. What v2 changes.** It receives the clip's episode logline and continuity notes, labelled "episode summary" and marked as context the viewer never sees. It says a cliffhanger can be emotional, romantic or visual. It returns needs_prior_context (true/false) and a short context_reason instead of free text. Score fields are the same. QA flags a v2 clip only when needs_prior_context is true. The prompt text uses no show-specific words.

**D35. Token budget.** The first v2 draft was estimated at about 194k tokens, too close to the 200k daily cap. I shortened the instructions and capped the summary at 360 characters, which brought the estimate to about 179k. Camera directions stay in the transcript because v2 needs them to see visual cliffhangers. A guard in judge.py stops the run before 192k tokens, and a 429 or quota error stops it after the first failure. llm.py no longer retries those errors.

**D36. The same 120 clips, judged again.** `run.py --rejudge-from outputs/groq_v1_final` reloads v1's saved shortlist and judges it with v2. Re-running the pipeline would have rebuilt the shortlist with the new rule scores, so v1 and v2 would not be comparable. groq_v2 was run with all Phase 1 fixes off (like groq_v1_final). final_v2 applies the fixes by rescoring groq_v2 with no further calls.

**D37. The run started at 05:35:22 IST**, after Groq's 05:30 reset, as instructed.

## Round 2, Phase 3: random gold set

**D38. 60 clips drawn at random (seed 11) from all 179 distinct moments of the rules-only run.** The pool was rebuilt with the round-1 rules (fixes off), which reproduces exactly 179 moments. The blind sheet showed transcripts only. Whether a clip was shortlisted was saved in a separate file that I opened only after labelling.

**D39. Labels: 13 YES, 27 MAYBE, 20 NO.** About half the clips are the same cuts I labelled in round 1, which I re-judged from the transcript. All 13 YES clips are single stretches and form eval/gold_random.yaml. The file header says the labels are AI-drafted and not from the tool's ranking.

**D40. Scoring against the random set.** Only 60 clips in 41 episodes were labelled, so most picks overlap no labelled clip. Recall is measured end to end: a YES clip the tool did not pick, including one that never reached the shortlist, is a miss. Precision is reported only over picks that overlap a labelled clip ("labelled" in the table), because an unlabelled pick is neither right nor wrong.

**D41. Shortlist coverage.** 12 of the 13 random YES clips were in v1's 120-clip shortlist, against 41 of the 60 random clips overall. So the rule shortlist catches almost every good clip, and most losses happen in ranking.

## Round 2, Phase 4: decision

**D42. Judge v2 is not promoted. v1 stays the main result.** The rule: promote only if the even split does not get worse on recall@15 and precision@15 AND the all-episode numbers improve. Even split: recall@15 5/14 for both, precision@15 5/8 for v2 against 5/9 for v1+fix. All episodes: recall@15 8/31 against 10/31, precision@15 8/15 against 10/15. All-episode numbers got worse, so v2 fails. outputs/final, README, SOLUTION_DOC numbers, INTERVIEW_PREP and raw_outputs_for_drive.zip are left as they were, apart from a short Round 2 paragraph.

**D43. The v2 run is incomplete and I did not resume it.** Groq stopped it at clip 87 on the tokens-per-day limit, and the rule for this round was to stop and report. A comparison on only the 86 clips both prompts judged gives the same numbers as the partial run, because the 34 unjudged clips were v1's lowest-ranked. outputs/final_v2 records unjudged_clips: 34 and the error in its run_meta.json.

**D44. The Phase 1 fixes stay on in config.yaml but are not in the main output.** They passed the tune and test rule and help slightly on top of v1 (outputs/r2_v1fix). The round's instruction was to leave the main files alone if v2 was not promoted, so switching the main result to v1 plus fixes is left to Swagat.

## Round 3, Phase 1: cross-validated re-blend (21 Nov 2026, branch round3, no LLM calls)

**D45. Learned re-blend: no gain, not adopted.** An L2-regularised logistic regression (L2 = 1.0, fixed in advance, no tuning) on 8 features of the 120 saved v1 clips, with 33 positive clips (matching the 31-clip gold set or the 13 random YES clips). Five folds grouped by episode (10 episodes each, seed 5). Held-out scores from all folds were stitched into one ranking and passed through the normal dedupe, top 25 and posting order. Against the current blend (0.4 rules + 0.6 LLM) under the same folds: gold recall@15 8/31 against 10/31, precision@15 8/15 against 10/15, folds won 1 of 5. Only recall@25 improved (14/31 against 12/31). The rule needed +2 at recall@15, no loss in precision, and 3 of 5 folds, so this fails on all three. Fold seeds 7 and 11 gave the same verdict (7/31 each).

**D46. rank_in_episode is partly circular.** The round-1 review sheet showed each episode's top 3 clips by this same v1 blend, and most gold clips came from that sheet. So rank-in-episode predicts gold partly by construction. Without it, the result is the same (8/31), so the conclusion does not depend on it.

**D47. What the weights say.** Trained on all 120 clips, on standardised features: rank in episode -0.78 (better-ranked clips in an episode are more often gold), LLM overall relative to its episode +0.74, clip is the episode's ending +0.67, rules cliffhanger +0.47, LLM cliffhanger +0.35, raw LLM overall -0.28, rules standalone +0.13, rules hook about 0. Hook barely matters once the other signals are known, and how a clip compares to its own episode matters more than its absolute LLM score.

**D48. Exported as config only, switched off.** ranking.learned_blend in config.yaml holds the feature names, weights, intercept, means and stds, with enabled: false and accepted_by_cv: false. promo_finder/learned.py applies it when enabled. With it off, output is identical to round 2.

## Round 3, Phase 2: listwise rerank (code and fake-server test only, no Groq calls)

**D49. A second stage that compares clips side by side, off by default.** After blending, the top 30 distinct clips go to the judge in batches of 10, as transcripts only (no scores, no episode summary), shuffled with a fixed seed. The judge returns them in order with one reason each. Two passes with different shuffles give each clip two positions in different company. The average becomes a 0 to 1 rank score, blended 0.7 blend + 0.3 rank. Only the order inside the top 30 changes: the 30 keep their band of final scores, and clips that overlap them stay below the band. Settings live under rerank: in config.yaml (enabled: false).

**D50. No camera lines in rerank prompts by default.** With camera lines a 10-clip batch is about 7k input tokens, which with output would break Groq's ~8k tokens-per-minute limit in a single call. Without them it is about 3.3k. Action and sound lines stay, so visual beats are still visible. Calls are spaced 60 s apart.

**D51. Batches depend on which clips they are, not on their scores.** The first test run showed that shuffling by score order changed the batches whenever scores changed, which means new prompts and new paid calls. Clips are now sorted by identity (episode and timestamps) before the seeded shuffle, so the same 30 clips always give the same 6 prompts and hit the cache.

**D52. Failure handling.** A clip missing from a reply, an unknown or repeated id, or a reply without a ranking list scores neutral (0.5) and is logged. A reply that is not JSON at all scores the batch neutral. A 429 or quota error stops the stage after one call and keeps the blend order. All of these are covered by tests against a fake OpenAI-compatible server.

**D53. Token estimate about 26k, measured, not guessed.** A dry run of the exact command against a local fake server sent 6 prompts of 10.9k to 12.7k characters (about 21k input tokens). The run is documented in docs/RUN_STAGE2.md, with --no-fixes (added; reproduces outputs/final exactly) for groq_v3 and --rerank-saved (re-applies saved scores, no calls) for final_v3.

## Adopting the main result (21 Nov 2026)

**D54. Main result is v1 plus the five round-2 rule fixes (outputs/final_main).** Swagat's call after comparing the top 10 lists by eye. The metric change is within noise (all-episode recall@10 6/31 to 8/31, recall@5 4/31 to 3/31, recall@15 10/31 and precision@15 10/15 unchanged). The reason is the top 10: it drops a happy, resolved ending (episode 4) and adds two strong clips (episodes 36 and 16). outputs/final_main matches outputs/r2_v1fix exactly (same picks, order and scores). outputs/final and outputs/groq_v1_final stay as the baseline.

**D55. Branches.** The default branch was called master. It was renamed to main (DEPLOY.md already did this at push time) and fast-forwarded to round3, which contains round2. No merge commits were needed because history is linear.

**D56. judge_version set back to v1 by default.** v2 was tried and not adopted. The main result uses v1 scores, so new runs should use the same prompt. The five fixes stay on by default; the learned blend and the rerank stage stay off. config.yaml tuning_log records all round 2 and 3 outcomes and is copied into run_meta.json.

**D57. Zip rebuilt.** raw_outputs_for_drive.zip now holds outputs/final_main (main), outputs/final and outputs/groq_v1_final (baseline), round2/groq_v2 and round2/final_v2 (judge v2 attempt), round3/cv_reblend_report.md (CV attempt), and a README.txt listing each. outputs/r2_v1fix is left out because it is identical to final_main. The round-3 rerank dry run is left out because its rankings came from a fake server.

**D58. No test changes were needed.** Every test that depends on a fix, the rerank stage or the learned blend sets its switch explicitly, so the new defaults did not break any. 34 passed.

## Final push (21 Nov 2026)

**D59. Round reports moved to docs/history/ with a banner.** REPORT.md, REPORT_ROUND2.md and REPORT_ROUND3.md each said a different run was the main result, because each was true when written. They now sit in docs/history/ under a banner that names outputs/final_main as the main result. Percentages in the round 1 report were replaced with counts, and the old rules-only rows are labelled "original rules" so they do not clash with the final rules-only row (7/31, 7/15). RUN_STAGE2.md moved to docs/.

**D60. PROMPTS.md untracked.** It was a planning file of prompts for driving Claude Code, not part of the tool. It stays on disk and is git-ignored. CLAUDE.md stays tracked because it states the project rules (no screenplay text in the repo, labels only edited by Swagat).

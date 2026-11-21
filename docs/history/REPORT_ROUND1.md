# Round 1 report

> Historical report, kept for the record. It describes the project at the end of that round. The main result is now outputs/final_main (v1 LLM scores plus five rule fixes); the final numbers are in README.md and REPORT_FINAL.md.

## Status

| Phase | Step | Status | Where |
|---|---|---|---|
| A | Label 207 clips (44 YES, 96 MAYBE, 67 NO) | done | eval/labels_draft.md |
| A | Gold set: 31 clips, 30 episodes, max 2 per episode | done | eval/gold_promos.yaml (old draft moved to gold_promos_old_draft.yaml) |
| A | 12 least certain labels | done | eval/labels_to_review.md |
| B | Evaluate LLM run and rules-only on all 50 episodes | done | eval/reports/ |
| B | Tune on odd episodes, test on even, max 5 changes | done (1 change tried, reverted) | config.yaml tuning_log, DECISIONS D19 |
| B | 5 instructive misses and false alarms | done | FAILURES.md F11 to F15 |
| C | Model swap | done with a fake provider (no second real key in .env) | tests/test_swap_provider.py, outputs/swap_test |
| C | README: plug in your own API | done | README.md |
| D | Messy new-input simulation | done, 3 bugs found and fixed | DECISIONS D21 |
| D | pytest suite | done, 15 passed | tests/ |
| E | outputs/final from saved scores, no LLM calls | done | outputs/final |
| E | raw_outputs_for_drive.zip | done (281 KB, 18 files) | project root |
| F | Pinned requirements, upload app, secrets, rules-only mode, local test | done | app.py, requirements.txt |
| F | git init, local commit, clean ls-files, DEPLOY.md | done, not pushed | DEPLOY.md |
| G | SOLUTION_DOC.md and PDF (2 pages) | done | SOLUTION_DOC.md, SOLUTION_DOC.pdf |
| G | INTERVIEW_PREP.md | done | INTERVIEW_PREP.md |

## Final numbers

Gold set: 31 AI-drafted clips across all 50 episodes, graded with `--covered 1-50`.

| Run | recall@5 | recall@10 | recall@15 | recall@25 | precision@15 |
|---|---|---|---|---|---|
| Rules only, original rules (outputs/rules_only_baseline) | 2/31 | 4/31 | 6/31 | 8/31 | 6/15 |
| Rules + Groq gpt-oss-120b (outputs/final) | 4/31 | 6/31 | 10/31 | 12/31 | 10/15 |

Best possible recall@15 is 15/31 (25 picks, 31 gold clips).

| Split | recall@15 before | recall@15 after | precision@15 before | precision@15 after |
|---|---|---|---|---|
| Tune (odd episodes) | 7/17 | 7/17 | 7/15 | 7/15 |
| Test (even episodes) | 5/14 | 5/14 | 5/9 | 5/10 with llm_weight 0.7, so reverted |

Final outputs use the original weights, so "after" equals "before" in outputs/final.

## WHAT SWAGAT MUST DO

1. Review eval/labels_to_review.md against eval/review_sheet.md, flip any disagreements in eval/gold_promos.yaml, then run `python eval/evaluate.py outputs/final/promos.json --k 5,10,15,25 --covered 1-50` and update the numbers in README.md and SOLUTION_DOC.md. (20 min)
2. Fill in the [[N labels changed after my review]] placeholder in SOLUTION_DOC.md, rewrite the doc in your own words, and re-export the PDF (Edge: open the .md rendered as HTML and print to PDF, or ask Claude to redo it). Answer interview question 20 for yourself. (40 min)
3. Create the GitHub repo and push, then deploy on Streamlit Community Cloud, following DEPLOY.md step by step. (20 min)
4. Upload raw_outputs_for_drive.zip to Google Drive and set sharing to "Anyone with the link, Viewer". (5 min)
5. Open every link (repo, app, Drive zip, solution doc) in a private window and check it loads. (5 min)
6. Submit the form: name, roll no 123BM0753, branch, Problem 1, and all links. (5 min)

## What I could not do, and why

- **Second real provider:** .env holds only the Groq key, so the swap test uses a local fake OpenAI-compatible server. It exercises the real HTTP code, but no second real model was called.
- **No new Groq calls:** following your rule. The confusing_for_new_viewer fix (a yes or no field) needs new calls, so it is described but not done.
- **Human review of the gold labels:** that needs you. My labels are not fully blind (DECISIONS D11), and 29 of 31 gold clips came from the tool's own shortlist (D13). Both flatter the numbers.
- **Push, deploy, Drive upload and form:** these need your accounts.
- **Task list:** this session had no task-list tool, so progress was tracked in this report and DECISIONS.md instead.
- **Small deviations to know about:**
  - **outputs/groq_v1_final:** its QA confidence fields were recomputed at your request before this push (D06). outputs/groq_v1 holds the untouched original.
  - **PROMPTS.md:** one screenplay line in it was replaced with a placeholder (D26).
  - **C: drive:** freed by purging pip's cache, 3.9 GB (D25).

## Round 2 (21 Nov 2026, branch round2)

Tried five rule fixes and a second judge prompt that also sees the episode summary. The rule fixes passed the tune/test check and help slightly on top of v1 (all-episode recall@10 6/31 to 8/31). Judge v2 made the scores bunch together (0 of 86 clips flagged as needing context) and lowered all-episode recall@15 from 10/31 to 8/31, so it was not promoted. The Groq run also stopped at clip 87 of 120 on the rolling tokens-per-day limit. The main result is still outputs/final. Details: REPORT_ROUND2.md.

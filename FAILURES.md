# Failures log

What went wrong, how it was found, and how it was fixed. Part 1 is tooling and process. Part 2 (added in Phase B) is where the promo picker itself chose badly.

## Part 1: tooling and process

**F01. pip install failed with "No space left on device".**
Found: the first `pip install -r requirements.txt` crashed while downloading. C: had 30 MB free and pip downloads into the C: temp folder.
Fixed: pointed TMP, TEMP and PIP_CACHE_DIR at E:\pip_tmp for installs. No code change.

**F02. promos.json was not valid UTF-8 on Windows.**
Found: reading promos.json with encoding="utf-8" failed on byte 0x97, the Windows cp1252 code for an em dash. The evaluator only worked because it also used the Windows default.
Fixed: every read_text, write_text and open() call now passes encoding="utf-8". Re-ran rules-only; recall and precision were unchanged (45% and 43%), and all output files decode as UTF-8.

**F03. Gemini free tier stopped the LLM run after about 23 calls.**
Found: gemini-2.5-flash returned 404 for new users, gemini-3.8-flash timed out and then returned 503, and gemini-3.5-flash worked but answered slowly (46 s for a tiny prompt). The full run then failed with 429 at 23 of 120 calls. The full error said "GenerateRequestsPerDayPerProjectPerModel-FreeTier, limit 20". llm.py cuts errors to 300 characters, which hid the quota name, so I sent one direct request to read the full message.
Fixed: stopped the run instead of letting 97 calls fail, then moved the judge to Groq (D02). Raising the delay between calls would not have helped with a daily cap.

**F04. Printing LLM text crashed on the Windows console.**
Found: a comparison script crashed with UnicodeEncodeError on U+2011 (non-breaking hyphen), which gpt-oss-120b writes in its answers. The Windows console uses cp1252.
Fixed: run.py and eval/evaluate.py switch stdout and stderr to UTF-8 at start. Tested with a hook containing U+2011: exits 0 and prints it. The same print without the fix still crashes.

**F05. confusing_for_new_viewer flagged 119 of 120 clips.**
Found: after the Groq run, 24 of the 25 final picks were "medium" confidence. The judge prompt asks for this field as free text ("what a stranger would not understand, or empty"), and the model almost always writes something like "who is Juliana".
Fixed in part: the QA rule now flags only three conditions (D07). With the confusing-text condition on, the split stays 1 high / 24 medium; with it off, 23 / 2. The real fix is to ask the judge for a yes/no field, which needs new LLM calls and was not done.

**F06. A cancelled monitor looked like a hung run.**
Found: progress messages stopped at 60 of 120 because the Claude Code session ended. Checking showed no python process, a log ending in "Done in 1555.5s", and 120 new cache files. The run had finished normally at 23:37.
Fixed: nothing to fix in the code. Lesson: check the log and the cache before assuming a hang.

**F07. `--provider none` would have called Groq anyway.**
Found: while planning offline runs I re-read llm.py. It takes the provider from the environment first, and .env sets groq. run.py only changed the config value.
Fixed: run.py now writes command-line choices into the environment (D09). Since the cache-key change (D05), this bug would have spent fresh Groq tokens on every "offline" run.

**F08. The first conflict word lists missed fire, explosion, whip and execution scenes.** (earlier session, recorded in SOLUTION_DOC_DRAFT.md)
Found: the lists were written while reading episodes 1 to 17. The fire (Ep 18), branding iron (Ep 31) and witch trial (Ep 33 to 34) ranked low.
Fixed: added genre-level words (fire, flame, explosion, fireball, whip, crop, branding, execution and similar). Scores on episodes 1 to 16 did not change. F11 below shows the words now exist but still carry little weight.

**F09. The evaluator wrote its report into the raw output folder.**
Found: while planning Phase B. Every `evaluate.py` run rewrote eval_report.md inside outputs/<run>/, so "unedited raw output" was not true.
Fixed: reports now go to eval/reports/ by default. The evaluator also gained several k values at once, an odd/even split, and a --covered option.

**F10. My first gold-set header called it an "Editor gold set".**
Found: re-reading the file after writing it. No editor made these labels.
Fixed: changed it to "Gold set".

## Part 2: where the picker chose badly (groq_v1_final against the new gold set)

Ranks below are positions among the 120 shortlisted clips sorted by final score. The final list holds 25. Clips are described in my own words, not quoted.

**F11. Explosion in the middle of the clip, ranked 73rd (gold G28, Ep 41).**
What the system did: rules gave cliff 0.35 and standalone 0.31. The LLM gave overall 6 with standalone 5 ("missing context").
Why it was wrong: the church doors explode about 23 seconds into the clip, but the cliff score only reads the last 6 seconds, which show armed figures walking in. The explosion words are in the lexicon now (F08), yet one physical word adds at most 0.2 to a line's heat. The standalone score also loses 0.24 to episode_depth_penalty at episode 41, and the LLM's own standalone score penalises the same late-episode problem, so it is counted twice.

**F12. A tender cliffhanger ranked 110th of 120 (gold G07, Ep 10).**
What the system did: rules gave cliff 0.20 and heat 0.04. The LLM gave overall 5 with "no context for the conflict".
Why it was wrong: the clip is pure romantic tension that ends before a kiss. Both judges look for conflict. The rules count anger words and the LLM prompt asks for "a slap, a reveal, a shocking or cruel line". The same thing happened to G26 (Ep 38, rank 70): she smiles and whispers her husband's name as the bells for her execution ring, and the calm-ending list matched the smile and the tender delivery, flagging an unresolved ending as resolved.

**F13. A visual transformation with a 0.17 hook score (gold G27, Ep 39).**
What the system did: rule hook 0.17, LLM standalone 3, rank 100.
Why it was wrong: the clip opens on an action line (the hero touching his scar), so no dialogue lands in the first 3 seconds and the hook is cut by 25%. The payoff is visual: he cuts his hair and appears as the Duke. A text-only scorer cannot see a costume reveal, and the LLM read the clip as missing context.

**F14. A resolved ending in the top 10 (pick #9, Ep 4).**
What the system did: rules flagged "ends on a calm / resolved beat" and gave cliff 0.19. The LLM gave hook 8 and overall 7, and the 0.6 LLM weight pulled the blend to 0.65.
Why it was wrong: the couple walk out into the sunlight as the episode fades. That is a happy ending, not a cliffhanger. The rule flag existed but only feeds the QA notes; nothing stops a strong hook from carrying a resolved ending into the top 10.

**F15. Two halves of one scene count as a miss and a false alarm (gold G01 vs pick #5, Ep 1).**
What the system did: picked 43.9 to 74.6 s (the accusation scene). The gold clip is 14.3 to 46.8 s (the altar reveal). The LLM rated the gold clip's opening 4 out of 10.
Why it was wrong, partly: the clips are neighbouring cuts of the same scene and share only 2.9 seconds, so the 50% overlap rule scores one miss and one false alarm. My gold choice here is debatable and is item 5 in labels_to_review.md. The lesson is that recall on a 31-clip gold set moves in large steps when one judgement call flips.

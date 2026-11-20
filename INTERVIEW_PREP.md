# Interview prep

Short, honest answers. Numbers come from outputs/final and eval/reports.

## 20 likely questions

**1. Why code first and the LLM second?**
Most of the job has a right answer: timestamps, shot boundaries, never cutting mid-line, 20 to 60 seconds. Code gets that right every time, for free. Taste is the only part that needs a model, so the LLM sees about 2.4 clips per episode instead of 13,000 cuts.

**2. Why blend 0.4 rules and 0.6 LLM?**
The LLM is the better judge: precision@15 is 67% for the blend against 40% for rules alone. The rules still catch things the LLM ignores, such as a mid-sentence opening or an episode's own written cliffhanger. I tested 0.7 on the tune split. It did not help the test split, so I kept 0.6.

**3. How did you build the gold set?**
I built a blind review sheet: the tool's top 3 clips per episode plus 2 random cuts, sorted by time, with no scores shown. Claude labelled all 207 clips from the transcripts and picked 31 YES clips, at most one per episode except episode 3. I am reviewing the 12 least certain labels.

**4. What is weak about that gold set?**
One labeller, and an AI. 29 of the 31 gold clips came from the tool's own shortlist, so recall is flattered. 31 clips is small, so one judgement call moves recall by about 3 points.

**5. What are the headline numbers?**
Recall@15 32%, precision@15 67%, against a maximum possible recall@15 of 48%, since the list has 25 picks for 31 gold clips. Rules alone: 19% and 40%.

**6. Did tuning help?**
No. Nine single changes on odd episodes. Only an LLM weight of 0.7 helped there, and it did not help on even episodes, so I reverted it. Most missed gold clips sit at ranks 33 to 104 of 120, too low for weight tweaks to rescue.

**7. What happens with a stronger model?**
Change three settings: provider, model, base URL. The rules shortlist stays the same, so the stronger model only re-judges about 120 clips. The biggest gain would come from letting it judge more clips per episode, because the misses were on the shortlist but ranked low.

**8. How would Kuku plug in its own API?**
PROMO_LLM_PROVIDER=openai_compatible, PROMO_LLM_MODEL, PROMO_LLM_BASE_URL, plus the key. A test runs the whole pipeline against a fake OpenAI-compatible server to prove it.

**9. Cost per episode?**
2.4 judge calls. The real run used 133,397 input and 35,550 output tokens for 50 episodes: about 2,700 in and 700 out per episode. On Groq's free tier it cost nothing. At paid prices it is a fraction of a cent per episode.

**10. How long does it take?**
Rules only: about 7 seconds for 50 episodes. With the LLM: 26 minutes, almost all of it the 13-second wait between calls to stay under Groq's free per-minute limit. Each call itself took about 1.3 seconds.

**11. How does it fail?**
Tender romance cliffhangers rank low, visual payoffs (an explosion mid-clip, a costume reveal) are under-read, and a strong hook can carry a resolved ending into the top 10. FAILURES.md has five real cases.

**12. What went wrong while building it?**
Windows encoding, Gemini's 20-requests-a-day free limit stopping the run after 23 calls, a lexicon written from the first 17 episodes only, a free-text field flagging 119 of 120 clips, and a bug where `--provider none` would still have called the paid model.

**13. How do you know the cuts are legal?**
The generator only cuts on shot boundaries where nobody is mid-line, and QA re-checks length and mid-line cuts on every pick. Tests cover both rules.

**14. What does the LLM actually see?**
Only the clip transcript with timestamps relative to the clip, never the show bible. That way it judges "does this make sense to a stranger" honestly.

**15. What is a cold open?**
A 2 to 6 second flash of the payoff, then the build-up that stops just before it. The flash must come from at most 25 seconds after the body, or from the next episode's opening, so it is never a random scene.

**16. What if the new show's files are messy?**
The parser skips bad blocks with a warning naming the file and line, takes numbers from file names when the header is missing, and reports gaps and duplicates. I tested it on renamed, reordered files with blank lines and a broken timing line.

**17. How do you stop the LLM budget leaking?**
Answers are cached on disk by provider, model, reasoning effort and prompt, so re-runs are free. `--rescore-from` re-ranks saved scores with no calls at all.

**18. Why is QA confidence mostly "medium"?**
The judge's "confusing for a new viewer" field is free text, and it fills it for 119 of 120 clips. Turning that condition off gives 23 high and 2 medium. The proper fix is a yes or no field.

**19. What would you build next?**
A yes or no confusion field, more clips per episode for the judge, cliffhanger scoring that reads visual directions, and a gold set labelled by a real editor from whole episodes.

**20. What did you personally decide versus the AI?**
Be ready to answer this in your own words. Name the decisions you made (code-first split, the cold-open idea, honest tuning, free tiers only) and the labels you changed after review.

## 3-minute walkthrough script (optional video)

- **0:00 to 0:20** Problem. "Kuku gave me 50 microdrama screenplays. I need 20 to 60 second promos with a hook, a cliffhanger, and a story a stranger can follow."
- **0:20 to 0:50** Approach. Show the pipeline table in README. "Code handles timestamps and legal cuts. The LLM only judges taste, on about 2.4 clips per episode."
- **0:50 to 1:30** Demo. Open the Streamlit app, upload a zip of three episodes, keep provider none, click Find promos. Point out the parse warnings box, a high-confidence pick, its hook, its cliffhanger and transcript.
- **1:30 to 2:00** Results. Show the results table. "The LLM judge raises precision@15 from 40% to 67%. I tuned on odd episodes and tested on even ones, and reverted the one change that did not hold up."
- **2:00 to 2:35** Failures. Show FAILURES.md. "Tender cliffhangers and visual payoffs rank low. A free-text field flagged 119 of 120 clips. Gemini's free tier stopped my first run, so I moved to Groq."
- **2:35 to 3:00** Swap and next steps. Show the three .env lines. "With Kuku's API this is a config change. Next I would make the confusion field yes or no, judge more clips per episode, and get an editor's gold set."

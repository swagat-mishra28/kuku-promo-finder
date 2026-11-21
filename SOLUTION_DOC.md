# Finding promos in microdrama screenplays

Swagat Mishra · Kuku AI Generalist assignment · Problem 1

Code: https://github.com/swagat-mishra28/kuku-promo-finder · Live app: https://kuku-promo-finder-awumukf6sgq3evtbmsljth.streamlit.app/ (try the invented sample show or upload screenplays; rules-only mode needs no key)

## Why this problem

I picked Problem 1 because it is the one where I could check whether I was right. Today an editor watches every episode to pick promos, and Kuku releases new shows every week, so a tool that does the first pass saves work on every show, not once. The input pack is real, and the output is a list of timestamps an editor can check in minutes: a clip either opens on a hook, cuts on an open question and makes sense to a stranger, or it does not. Problem 2 needed legal answers I could not verify in a few hours, and Problem 3 meant guessing at a problem when Kuku had already named a real one.

## Assumptions

- Screenplay timestamps match the finished video, so a timestamp range is a usable cut.
- A cut may land only on a shot boundary, never in the middle of a line, and a promo is 20 to 60 seconds.
- "Joining a few moments" means a cold open: a 2 to 6 second flash of the payoff (from at most 25 seconds later, or the next episode's opening), then the build-up that stops just before it. Freer montages are out of scope.
- A stranger knows nothing about the show, so the judge sees only the clip, never the show bible.
- Kuku wants a ranked list of about 25 to post in order. Early episodes get a small boost, because a promo sends viewers to episode 1.
- The tool reads text only, so purely visual payoffs, such as a costume reveal, cannot be judged.

## How it works

1. **Parse (code).** Each screenplay becomes timestamped camera, action, dialogue and sound events. Bad lines are skipped with a warning naming the file and line.
2. **Cut (code).** Every legal cut is generated: about 13,250 for 50 episodes, plus cold opens. Every cut is legal by construction.
3. **Score and shortlist (code).** Rules score the hook, cliffhanger, standalone sense, conflict and length, then remove duplicates. Each episode's own ending always reaches the shortlist, because writers end episodes on a cliffhanger.
4. **Judge (LLM).** Groq's openai/gpt-oss-120b re-scores the 120 shortlisted clips, about 2.4 per episode, as a cold viewer would.
5. **Rank and check (code).** The final score is 0.4 rules plus 0.6 LLM. A posting order spreads the picks across episodes. QA re-checks every pick and sends anything below "high" confidence to an editor, with the reason.

## How I know it's good

The gold set has 31 clips across all 50 episodes. **AI (Claude) drafted the labels from the transcripts.** I then reviewed every one, reading the lines around each cut, and kept all of them unchanged.

| Run | recall@5 | recall@10 | recall@15 | recall@25 | precision@15 |
|---|---|---|---|---|---|
| Rules only | 2/31 | 5/31 | 7/31 | 10/31 | 7/15 |
| LLM judge, original rules | 4/31 | 6/31 | 10/31 | 12/31 | 10/15 |
| LLM judge + five rule fixes (main result) | 3/31 | 8/31 | 10/31 | 12/31 | 10/15 |

The list has 25 picks for 31 gold clips, so the best possible recall@15 is 48%. Two of every three top-15 picks are gold clips. On a second gold set of 13 clips drawn at random from all candidate moments, the main result finds 5 at recall@15. I tuned on odd episodes and tested on even ones. A weight change that helped the tune split did not hold on the test split, so I reverted it. The five rule fixes came from reading failures, not from a search. They do not change recall@15, but they move a resolved, happy ending out of the top 10.

## Where it fails

- **Tender cliffhangers rank low.** A romance beat that cuts just before a kiss ranked 110th of 120: both the rules and the judge look for conflict.
- **Most picks are flagged for review.** I asked the judge what a stranger would not understand, "or empty". It wrote something for 119 of 120 clips, so most picks show medium confidence. A yes or no field would fix this.
- **The gold set flatters recall.** 29 of the 31 gold clips came from the tool's own shortlist, and one person checked one AI's labels. An editor choosing freely would be the real test.
- **Two ideas that did not work.** A judge that also saw the episode summary rated nearly every clip understandable (recall@15 8/31). A learned blend of the scores lost under cross-validation (8/31). Neither is used.

## AI tools, and where they got it wrong

I used Claude Code (Claude) to write most of the code with me, to draft the gold labels I then reviewed, and to help write these docs. The judge is Groq's openai/gpt-oss-120b. Gemini was my first judge.

- **Lexicon gap.** The first conflict word lists were written from episodes 1 to 17, with no fire, explosion or execution words, so later fire and witch-trial scenes ranked low. The cliffhanger score also read only the last 6 seconds. Both are fixed.
- **A cost bug.** `--provider none` would still have called the paid model, because a setting in `.env` won. A test now guards against it.
- **Free tier.** Gemini's free tier stopped my first run after about 23 calls (a limit of 20 a day), so I moved the judge to Groq.

## Scale and cost

- **A new show** is a folder of .txt files: one command, or an upload in the app. Rules-only mode takes about 7 seconds for 50 episodes.
- **LLM cost.** About 2,700 input and 700 output tokens per episode (133k and 36k for 50 episodes), free on Groq's free tier. The run took 26 minutes only because of the free tier's per-minute limit. Each call took about 1.3 seconds, so a paid API would finish in minutes. Answers are cached, and re-ranking from saved scores needs no calls.
- **Swapping the model** takes three settings (provider, model, base URL). Any OpenAI-compatible API works, and a test runs the whole pipeline against a fake one.
- **The editor stays in the loop.** They review only the ranked picks and the flags, instead of watching every episode.
- **Not yet general.** The word lists are English and written for one genre. Other languages need new lists, or more of the judging moved to the model.

## Next, with a stronger model

Make the confusion field yes or no, and let the model judge more clips per episode, because nearly every missed gold clip was on the shortlist but ranked low. Read cliffhangers from the visual directions as well as the last line. Have an editor build a gold set from whole episodes, and, with video access, check the cuts against the footage.

# Finding promos in microdrama screenplays

Swagat Mishra, Kuku AI Generalist assignment, Problem 1

## Problem and approach

Kuku gave me 50 timestamped screenplays of one microdrama. The task is to find 20 to 60 second clips that work as paid social promos: a hook in the first 3 seconds, a cut on an unresolved moment, and a story a stranger can follow. The tool must rank them and admit where it picks badly.

I split the work in two. Code does everything that has a right answer: parsing timestamps, cutting only on shot boundaries and never mid-line, checking length, removing duplicates and ranking. An LLM does only the part that needs taste, which is judging a short list of clips the way a cold viewer would. This keeps the expensive model to about 2.4 calls per episode, makes every cut legal by construction, and lets Kuku swap in a stronger model by changing three settings.

## How the pipeline works

1. The parser turns each screenplay into timestamped camera, action, dialogue and sound events. Bad lines are skipped with a warning that names the file and line.
2. The generator makes every legal cut: about 13,250 for 50 episodes. It also builds "cold opens", where a 2 to 6 second flash of the payoff plays first, followed by the build-up that stops just before it.
3. Rules score each cut for hook, cliffhanger, standalone sense, conflict density and length.
4. Duplicates are removed. Each episode's own ending always reaches the shortlist, because writers already end episodes on a cliffhanger.
5. The LLM judge (Groq, openai/gpt-oss-120b) re-scores 120 shortlisted clips. It sees only the clip, never the show bible.
6. The final score is 0.4 rules plus 0.6 LLM. A posting order then spreads episodes and slightly favours early ones, which send viewers to episode 1.
7. QA checks each pick and sends anything below "high" confidence to an editor.

## Results

I graded against a 31-clip gold set covering all 50 episodes. **The gold labels were drafted by AI (Claude) from the transcripts, and my own review is still pending.** [[N labels changed after my review]]

| Run | recall@5 | recall@10 | recall@15 | recall@25 | precision@15 |
|---|---|---|---|---|---|
| Rules only | 2/31 | 5/31 | 7/31 | 10/31 | 7/15 |
| LLM judge, original rules (v1) | 4/31 | 6/31 | 10/31 | 12/31 | 10/15 |
| LLM judge + five rule fixes (main result) | 3/31 | 8/31 | 10/31 | 12/31 | 10/15 |

The list holds 25 picks for 31 gold clips, so the best possible recall@15 is 48%. One clip is about 3 points. Two of every three clips in the top 15 are ones the gold set also chose. On a second gold set of 13 YES clips drawn at random from all candidate moments, the main result finds 5 at recall@15.

I tuned honestly, with odd episodes as the tune split and even episodes as the test split. Weight changes did not hold up on the test split, so the blend stays at 0.4 rules and 0.6 LLM. The five rule fixes came from the failure analysis below, not from a search. Their effect on the metric is within noise: about 2 clips at recall@10 and none at recall@15. I chose them because they remove a resolved, happy ending from the top 10 and add two strong clips in its place.

## Where AI got it wrong

- **Windows encoding.** The first outputs were written in the Windows default encoding, not UTF-8, and later the console crashed printing a non-breaking hyphen from the LLM. Every file read and write now names UTF-8, and the scripts set their console to UTF-8.
- **Free tier limits.** Gemini's free tier stopped my first LLM run after about 23 calls. The error showed a limit of 20 requests a day for that model. Waiting longer between calls would not help with a daily cap, so I moved the judge to Groq, which allows about 1,000 a day. The full run then cost 133k input and 36k output tokens.
- **Lexicon gap.** My first conflict word lists came from episodes 1 to 17 and had no fire, explosion, whip or execution words, so the fire, branding iron and witch trial scenes ranked low. I added them. Later I found the cliffhanger score only read the last 6 seconds, so a big beat just before the cut counted for nothing; it now gets credit up to 12 seconds back.
- **A free-text field became a constant flag.** I asked the judge what a stranger would not understand, "or empty". It wrote something for 119 of 120 clips, so almost every pick was flagged for review. A yes or no field would fix this. That needs new LLM calls, which I did not make.
- **Tender cliffhangers rank low.** A romance beat that ends before a kiss ranked 110th of 120. Both judges look for conflict, and the rules' "calm ending" words matched a soft delivery note, even though the scene was unresolved. Delivery words no longer count as an ending, but tender clips still rank low.

## Later attempts that did not work

- A second judge prompt that also saw the episode summary rated almost every clip understandable, its scores bunched together, and recall@15 fell to 8/31. Not used.
- A logistic re-blend learned from the labels lost under episode-grouped cross-validation (recall@15 8/31 against 10/31). Not used.

## Limits

The gold set is small and has one labeller, and that labeller was an AI. 29 of the 31 gold clips came from the tool's own shortlist, because the review sheet showed the tool's top 3 clips per episode plus 2 random ones. This makes recall look better than it would against an editor's free choice. The rules are written in English for one genre. A text-only judge cannot see visual payoffs such as a costume reveal. A pipeline bug also once let `--provider none` call the paid model; a test now guards against it.

## With a stronger model and more time

I would make confusing_for_new_viewer a yes or no field and let a stronger model judge more clips per episode, because nearly every missed gold clip was on the shortlist but ranked low. I would have a real editor label a gold set chosen from the whole episode, not from my shortlist. I would also read cliffhangers from the visual directions as well as the last line. With video access, I would check the cuts against the actual footage.

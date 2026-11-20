# Project notes for Claude Code

This is Swagat's submission for Kuku's AI Generalist assignment, Problem 1 ("Find the Promos").
Brief: given timestamped microdrama screenplays, find 20-60 s promo clips (one stretch or a few
joined moments) that open on a hook in the first 3 s, end on an unresolved cliffhanger, and make
sense to a stranger. Rank them, and report where the tool picks badly. Swappable model matters:
in the interview the tool will be run on a new show, possibly with a stronger model through an
API Kuku provides.

## Rules for working here
- The screenplays in data/episodes/ are confidential. Never commit them, never paste them into
  public places, never put transcripts in the public repo. outputs/ is git-ignored for this reason.
- Keep the split: deterministic code for parsing, cutting, validation and ranking; the LLM only
  for judgment (judge.py). Do not move timestamp logic into the LLM.
- Never invent gold labels in eval/gold_promos.yaml. Only Swagat edits that file. You may build
  review sheets that help him label.
- All tunables go in config.yaml, not hard-coded.
- After any change to scoring or ranking: run `python run.py` and `python eval/evaluate.py` on the
  newest outputs and report recall@15 / precision@15 before and after.
- Free tiers only. Respect rate limits (llm.min_seconds_between_calls). LLM responses are cached
  in .cache/llm, so delete that folder only when the prompt or model changes on purpose.
- Writing style for docs: plain, specific, short. No hype words, no em-dash chains, no "not only
  X but also Y", no lists of three for rhythm.

## Commands
- `python -m promo_finder.parser data/episodes` sanity-check parsing (events, lines, shots, length)
- `python run.py [--provider gemini --model gemini-2.5-flash] [--episodes DIR] [--out DIR]`
- `python eval/evaluate.py outputs/<run>/promos.json --k 15`
- `streamlit run app.py`

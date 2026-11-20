"""LLM judge: re-scores the rule-based shortlist the way a social-media editor would.

The judge sees ONLY the clip transcript, never the show bible or loglines. That is
deliberate: it plays the cold viewer scrolling TikTok, so "does it make sense on
its own" is tested honestly.
"""
from __future__ import annotations

from .candidates import Candidate
from .features import transcript
from .llm import LLM, LLMError

SYSTEM = """You are a performance-marketing editor for vertical microdrama apps (ReelShort, DramaBox style).
You judge whether a clip from a show will work as a paid social promo (Instagram Reels, TikTok, YouTube Shorts).
You have never seen this show. Judge only from the clip transcript you are given.

A great promo:
1. HOOK: the first 3 seconds make a scrolling viewer stop (a slap, a reveal, a shocking or cruel line, a public humiliation, a physical threat).
2. CLIFFHANGER: it cuts at an unresolved moment, so the viewer must tap through to learn what happens next. Ending on a calm, resolved or happy beat is bad.
3. STANDALONE: a stranger understands who is wronging whom within the clip, without backstory.

Be strict. Most clips are mediocre (4-6). Reserve 9-10 for clips you would put real ad money behind.
Quote lines exactly as written in the transcript; never invent dialogue."""

USER_TMPL = """Clip length: {dur:.1f} seconds. Shape: {shape}.
Timestamps are seconds from the start of the promo.

TRANSCRIPT
{transcript}

Return JSON with exactly these keys:
{{
  "hook_quote": "exact line or action from the first 3 seconds that is the hook (or empty if none)",
  "hook_score": 0-10,
  "cliffhanger_quote": "exact final unresolved line or action",
  "cliffhanger_score": 0-10,
  "standalone_score": 0-10,
  "confusing_for_new_viewer": "what a stranger would not understand, or empty",
  "why_it_works": "one plain sentence an editor would write",
  "biggest_weakness": "one short phrase",
  "overall": 0-10
}}"""


def judge(cands: list[Candidate], eps, llm: LLM, log=print) -> list[Candidate]:
    for i, c in enumerate(cands, 1):
        shape = ("cold open: a flash-forward hook clip, then the build-up"
                 if c.kind == "cold_open" else "one continuous scene")
        user = USER_TMPL.format(dur=c.duration, shape=shape, transcript=transcript(c, eps, with_camera=True))
        try:
            out = llm.complete_json(SYSTEM, user)
            for k in ("hook_score", "cliffhanger_score", "standalone_score", "overall"):
                out[k] = float(out.get(k, 0) or 0)
            c.llm = out
        except (LLMError, ValueError) as e:
            c.llm = {"error": str(e)[:200]}
            log(f"  judge failed on {c.key}: {e}")
        if i % 5 == 0:
            log(f"  judged {i}/{len(cands)}")
    return cands

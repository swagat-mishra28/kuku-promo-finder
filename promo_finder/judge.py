"""LLM judge: re-scores the rule-based shortlist the way a social-media editor would.

Two prompt versions, chosen by llm.judge_version in config.yaml:

v1  The judge sees ONLY the clip transcript. It plays the cold viewer scrolling
    TikTok. Kept unchanged so earlier runs stay reproducible from the cache.
v2  Adds the episode's logline and continuity notes, labelled "episode summary",
    so the judge understands the scene, while still scoring as a cold viewer.
    Says plainly that a cliffhanger can be emotional, romantic or visual.
    Replaces the free-text confusing_for_new_viewer (filled for 119 of 120 clips
    in v1) with needs_prior_context true/false plus a short reason.
Both return the same score fields, so the rest of the pipeline is unchanged.
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

PROMPT_VERSION_V2 = "judge-v2-2026-11-21"

SYSTEM_V2 = f"""[{PROMPT_VERSION_V2}] You are a performance-marketing editor for vertical microdrama apps.
Score a clip as a paid social promo (Reels, TikTok, Shorts) for a cold viewer who sees only this clip.
The episode summary is for your understanding only; the viewer never sees it.
HOOK: the first 3 s stop a scroll (shocking line, reveal, threat, humiliation, striking action).
CLIFFHANGER: it cuts while something is unresolved. It may be a threat or shock, or emotional, romantic or visual (a confession left hanging, a near-kiss, a held shot, a reveal, a transformation). A settled or happy ending is bad.
STANDALONE: from the clip alone, a stranger can tell who wants what and who is wronging whom.
Be strict: most clips are 4-6; 9-10 only for clips worth real ad money. Quote lines exactly; never invent dialogue."""

USER_TMPL_V2 = """EPISODE SUMMARY: {summary}

Clip: {dur:.1f} s, {shape}. Timestamps are seconds from the clip start.
TRANSCRIPT
{transcript}

Return JSON with exactly these keys: hook_quote (exact line or action from the first 3 s, or empty), hook_score (0-10), cliffhanger_quote (exact final unresolved line or action), cliffhanger_score (0-10), standalone_score (0-10), needs_prior_context (true only if a stranger could not follow the clip at all, else false), context_reason (short phrase or empty), why_it_works (one plain sentence), biggest_weakness (short phrase), overall (0-10)."""

SCORE_KEYS = ("hook_score", "cliffhanger_score", "standalone_score", "overall")


class StopJudging(RuntimeError):
    """Raised on a rate-limit or quota error: stop calling, never loop."""


def episode_summary(c: Candidate, eps) -> str:
    ep = eps[c.segments[-1].episode]
    parts = [p for p in (ep.logline, ep.continuity) if p]
    text = " ".join(parts)
    return (text[:360].rsplit(" ", 1)[0] + "..." if len(text) > 360 else text) or "(none)"


def _as_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "yes", "1", "y")


def parse_judge_output(out: dict, version: str = "v1") -> dict:
    """Normalise one judge answer: scores to float 0-10, v2 context flag to a real bool."""
    out = dict(out)
    for k in SCORE_KEYS:
        try:
            out[k] = max(0.0, min(10.0, float(out.get(k, 0) or 0)))
        except (TypeError, ValueError):
            out[k] = 0.0
    if version == "v2":
        out["needs_prior_context"] = _as_bool(out.get("needs_prior_context", False))
        out["context_reason"] = str(out.get("context_reason", "") or "")[:200]
        out["prompt_version"] = PROMPT_VERSION_V2
    return out


def build_prompt(c: Candidate, eps, version: str = "v1") -> tuple[str, str]:
    shape = ("cold open: a flash-forward hook clip, then the build-up"
             if c.kind == "cold_open" else "one continuous scene")
    tx = transcript(c, eps, with_camera=True)
    if version == "v2":
        return SYSTEM_V2, USER_TMPL_V2.format(summary=episode_summary(c, eps), dur=c.duration, shape=shape,
                                              transcript=tx)
    return SYSTEM, USER_TMPL.format(dur=c.duration, shape=shape, transcript=tx)


def _is_quota_error(e: Exception) -> bool:
    t = str(e).lower()
    return " 429" in t or "rate limit" in t or "rate_limit" in t or "quota" in t or "tokens per day" in t


def judge(cands: list[Candidate], eps, llm: LLM, log=print, version: str = "v1") -> list[Candidate]:
    budget = getattr(llm, "max_run_tokens", 0) or 0
    for i, c in enumerate(cands, 1):
        used = llm.tokens_in + llm.tokens_out
        if budget and llm.calls and used + used / llm.calls > budget:
            log(f"  STOPPED at clip {i}/{len(cands)}: next call would pass the {budget:,} token budget ({used:,} used).")
            for rest in cands[i - 1:]:
                rest.llm = {"error": "not judged: token budget reached"}
            raise StopJudging(f"token budget {budget} reached after {llm.calls} calls")
        system, user = build_prompt(c, eps, version)
        try:
            c.llm = parse_judge_output(llm.complete_json(system, user), version)
        except (LLMError, ValueError) as e:
            c.llm = {"error": str(e)[:200]}
            log(f"  judge failed on {c.key}: {e}")
            if _is_quota_error(e):
                log(f"  STOPPED at clip {i}/{len(cands)}: rate limit or quota error. No further calls.")
                for rest in cands[i:]:
                    rest.llm = {"error": "not judged: run stopped on a rate-limit error"}
                raise StopJudging(str(e)[:300]) from e
        if i % 5 == 0:
            log(f"  judged {i}/{len(cands)}")
    return cands

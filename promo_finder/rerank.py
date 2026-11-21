"""Optional second stage: listwise rerank of the top clips (rerank.enabled in config.yaml, off by default).

After blending, the top_k clips (default 30) are shown to the judge in batches of
10, as transcripts only (no scores, no episode summary), shuffled with a fixed
seed. The judge returns them in order from most to least promo-worthy with one
reason each. A second pass uses a different shuffle, so every clip is ranked in
two different company sets. Positions are averaged into a 0-1 rank score, which
is blended with the existing score. Only the order inside the top_k changes:
the top_k keep their band of final scores, so nothing below can jump in.

Works with any provider through LLM.complete_json. Answers are cached by prompt
(the prompt carries RERANK_VERSION).
"""
from __future__ import annotations

import random

from .features import transcript
from .llm import LLM, LLMError

RERANK_VERSION = "listwise-v1-2026-11-21"

SYSTEM = f"""[{RERANK_VERSION}] You are a performance-marketing editor for vertical microdrama apps.
You compare clips as paid social promos (Reels, TikTok, Shorts) for a cold viewer who has never seen the show.
A strong promo stops a scroll in the first 3 seconds, cuts while something is unresolved (a threat, a shock,
a confession, a near-kiss, a reveal), and makes sense on its own. Judge only the transcripts given."""

USER_TMPL = """Rank these {n} clips from most to least promo-worthy.

{clips}

Return JSON: {{"ranking": [{{"id": "<clip id>", "reason": "<one short line>"}}, ...]}} with every id exactly once."""


def _batch_prompt(batch, eps, with_camera: bool) -> str:
    parts = []
    for cid, c in batch:
        parts.append(f"CLIP {cid} ({c.duration:.0f} s)\n{transcript(c, eps, with_camera=with_camera)}")
    return USER_TMPL.format(n=len(batch), clips="\n\n".join(parts))


def parse_ranking(out: dict, ids: list[str]) -> tuple[dict, list[str]]:
    """Map id -> position score in [0, 1] (1 = best) and a list of problems.

    Unknown ids and repeats are ignored. A clip missing from the reply gets 0.5 (neutral)."""
    problems = []
    raw = out.get("ranking") if isinstance(out, dict) else None
    if not isinstance(raw, list):
        return {i: 0.5 for i in ids}, ["reply has no 'ranking' list; batch scored neutral"]
    order = []
    for item in raw:
        cid = item.get("id") if isinstance(item, dict) else item
        cid = str(cid).strip() if cid is not None else ""
        if cid in ids and cid not in order:
            order.append(cid)
        elif cid not in ids:
            problems.append(f"unknown id {cid!r} ignored")
    n = len(ids)
    scores = {cid: (n - 1 - k) / (n - 1) if n > 1 else 1.0 for k, cid in enumerate(order)}
    for cid in ids:
        if cid not in scores:
            scores[cid] = 0.5
            problems.append(f"clip {cid} missing from the reply; scored neutral")
    return scores, problems


def batches_for_pass(n_clips: int, batch_size: int, seed: int) -> list[list[int]]:
    idx = list(range(n_clips))
    random.Random(seed).shuffle(idx)
    return [idx[i:i + batch_size] for i in range(0, n_clips, batch_size)]


def rerank(ranked, eps, llm: LLM, cfg: dict, log=print) -> dict:
    """ranked: clips already ordered by final score (best first). Reorders the top_k in place by
    blending the listwise rank score into final. Returns a summary for run_meta."""
    rc = cfg.get("rerank", {})
    k, size, weight = rc.get("top_k", 30), rc.get("batch_size", 10), rc.get("weight", 0.3)
    seeds = rc.get("seeds", [17, 29])
    top = ranked[:k]
    if len(top) < 2:
        return {"reranked": 0}
    # Batches depend on which clips they are, not on their current scores, so the same clips always
    # give the same prompts (and cache hits).
    stable = sorted(range(len(top)), key=lambda i: top[i].key)
    pos = {i: [] for i in range(len(top))}
    problems = []
    calls = 0
    for p, seed in enumerate(seeds, 1):
        for b, slots in enumerate(batches_for_pass(len(top), size, seed), 1):
            members = [stable[j] for j in slots]
            batch = [(f"C{j + 1}", top[i]) for j, i in enumerate(members)]
            ids = [cid for cid, _ in batch]
            try:
                out = llm.complete_json(SYSTEM, _batch_prompt(batch, eps, rc.get("with_camera", False)))
                calls += 1
                scores, probs = parse_ranking(out, ids)
            except (LLMError, ValueError) as e:
                if " 429" in str(e) or "quota" in str(e).lower():
                    log(f"  rerank STOPPED on a rate-limit error in pass {p} batch {b}; keeping the blend order")
                    return {"reranked": 0, "stopped_on_error": str(e)[:300], "calls": calls}
                scores, probs = {cid: 0.5 for cid in ids}, [f"bad reply ({str(e)[:80]}); batch scored neutral"]
            problems += [f"pass {p} batch {b}: {x}" for x in probs]
            for (cid, _), i in zip(batch, members):
                pos[i].append(scores[cid])
            log(f"  rerank pass {p} batch {b} done")
    band = sorted((c.final for c in top), reverse=True)
    lo, hi = min(band), max(band)
    span = (hi - lo) or 1.0
    combined = []
    for i, c in enumerate(top):
        rank_score = sum(pos[i]) / len(pos[i])
        c.llm["rerank_score"] = round(rank_score, 3)
        combined.append(((1 - weight) * (c.final - lo) / span + weight * rank_score, i))
    # Same band of finals, new order: nothing outside the top_k can be pushed in or out.
    for (_, i), f in zip(sorted(combined, reverse=True), band):
        top[i].final = f
    for p in problems:
        log(f"  rerank note: {p}")
    return {"reranked": len(top), "calls": calls, "weight": weight, "version": RERANK_VERSION,
            "problems": problems}


def apply_saved(ranked, cfg: dict) -> int:
    """Re-apply rerank scores saved in a previous run (no calls). Returns how many clips had one."""
    rc = cfg.get("rerank", {})
    top = [c for c in ranked[: rc.get("top_k", 30)] if "rerank_score" in c.llm]
    if len(top) < 2:
        return 0
    weight = rc.get("weight", 0.3)
    band = sorted((c.final for c in top), reverse=True)
    lo, span = min(band), (max(band) - min(band)) or 1.0
    order = sorted(top, key=lambda c: (1 - weight) * (c.final - lo) / span + weight * c.llm["rerank_score"],
                   reverse=True)
    for c, f in zip(order, band):
        c.final = f
    return len(top)

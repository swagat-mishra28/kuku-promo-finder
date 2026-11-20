"""End-to-end: screenplays -> ranked promo list + quality report.

  1. parse        (code)   screenplay text -> timestamped events
  2. generate     (code)   every legal 20-60 s cut: ~20k candidates for 17 episodes
  3. rule score   (code)   hook / cliff / standalone / heat, free and instant
  4. dedupe       (code)   keep the best version of each moment
  5. LLM judge    (AI)     re-score a shortlist as a cold viewer (optional, swappable)
  6. rank         (code)   blend scores, then pick a posting order with variety
  7. QA           (code)   hard checks + flags; low-confidence picks go to a human
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .candidates import (Candidate, cold_open_candidates, cut_points, hook_clips,
                         single_candidates, tc, _straddles)
from .features import line_heat, score_candidate, transcript
from .judge import judge
from .llm import LLM
from .parser import load_show


def overlap(a: Candidate, b: Candidate) -> float:
    """Shared screen time / shorter clip length (0..1)."""
    shared = 0.0
    for sa in a.segments:
        for sb in b.segments:
            if sa.episode == sb.episode:
                shared += max(0.0, min(sa.end, sb.end) - max(sa.start, sb.start))
    return shared / max(1e-6, min(a.duration, b.duration))


def same_payoff(a: Candidate, b: Candidate) -> bool:
    la, lb = a.segments[-1], b.segments[-1]
    return la.episode == lb.episode and abs(la.end - lb.end) < 2.5


def dedupe(cands: list[Candidate], max_overlap: float, key=lambda c: c.score) -> list[Candidate]:
    kept: list[Candidate] = []
    for c in sorted(cands, key=key, reverse=True):
        if all(overlap(c, k) <= max_overlap and not same_payoff(c, k) for k in kept):
            kept.append(c)
    return kept


def rules_for_blend(c: Candidate, cfg) -> float:
    """Rule score used in the blend. With fix_depth_once, the episode-depth penalty is dropped when the
    LLM has judged standalone sense, so late episodes are not penalised twice."""
    if cfg["scoring"].get("fix_depth_once") and c.llm and "standalone_score" in c.llm:
        f = c.features
        if "standalone_nodepth" in f:
            return c.score + cfg["scoring"]["weights"]["standalone"] * (f["standalone_nodepth"] - f["standalone"])
    return c.score


def blended(c: Candidate, cfg) -> float:
    if c.llm and "overall" in c.llm:
        l = c.llm
        llm_score = (0.30 * l["hook_score"] + 0.30 * l["cliffhanger_score"]
                     + 0.20 * l["standalone_score"] + 0.20 * l["overall"]) / 10.0
        w = cfg["ranking"]["llm_weight"]
        return (1 - w) * rules_for_blend(c, cfg) + w * llm_score
    return c.score


def resolved_ending(c: Candidate, cfg) -> bool:
    """Both judges agree the clip ends settled: rules flag a calm ending and the LLM rates the cliff low."""
    lim = cfg["ranking"].get("resolved_llm_cliff_max", 6)
    return ("ends on a calm / resolved beat" in c.features.get("flags", [])
            and c.llm.get("cliffhanger_score", 10) < lim)


def set_finals(shortlist: list, cfg) -> None:
    """Final score for every shortlisted clip. With fix_cap_resolved, a resolved ending can never
    outrank a clip with an open ending."""
    for c in shortlist:
        c.final = round(blended(c, cfg), 4)
    if cfg["ranking"].get("fix_cap_resolved"):
        open_finals = [c.final for c in shortlist if not resolved_ending(c, cfg)]
        if open_finals:
            floor = min(open_finals)
            for c in shortlist:
                if resolved_ending(c, cfg) and c.final >= floor:
                    c.final = round(floor - 0.0001, 4)


def qa(c: Candidate, eps, cfg) -> dict:
    f = c.features
    checks = {
        "length_20_60s": cfg["min_len"] <= c.duration <= cfg["max_len"],
        "no_line_cut_mid_sentence": all(not _straddles(eps[s.episode], s.start) and
                                        not _straddles(eps[s.episode], s.end) for s in c.segments),
        "hook_in_first_3s": f["hook"] >= 0.35,
        "ends_unresolved": f["cliff"] >= 0.35 and "ends on a calm / resolved beat" not in f["flags"],
        "understandable_cold": f["standalone"] >= 0.5,
    }
    hard_fail = not (checks["length_20_60s"] and checks["no_line_cut_mid_sentence"])
    rule_issues = [k for k, v in checks.items() if not v] + list(f["flags"])

    if c.llm and "overall" in c.llm:
        # LLM-judged: only these three reasons send a clip to the editor (hard fails always do).
        q = cfg["qa"]
        reasons = []
        if "needs_prior_context" in c.llm:   # judge v2: a real true/false answer
            if c.llm["needs_prior_context"]:
                reasons.append("LLM: needs prior context: " + (c.llm.get("context_reason") or "")[:140])
        else:                                # judge v1: free text, almost always filled
            confusing = (c.llm.get("confusing_for_new_viewer") or "").strip()
            if confusing and q.get("flag_on_confusing_text", True):
                reasons.append("LLM: confusing for a new viewer: " + confusing[:140])
        if c.llm.get("standalone_score", 10) < q.get("min_llm_standalone", 5):
            reasons.append(f"LLM standalone score {c.llm['standalone_score']:.0f}/10 is below {q.get('min_llm_standalone', 5)}")
        gap = abs(c.score - c.llm["overall"] / 10.0)
        if gap > q["disagreement_gap"]:
            reasons.append(f"rules and LLM disagree (rules {c.score:.2f} vs LLM {c.llm['overall']/10:.2f})")
        if hard_fail:
            reasons = [k for k in ("length_20_60s", "no_line_cut_mid_sentence") if not checks[k]] + reasons
        conf = "low" if hard_fail else ("medium" if reasons else "high")
        notes = [i for i in rule_issues if i not in reasons]  # rule-based notes, informational only
        return {"checks": checks, "issues": reasons, "notes": notes, "confidence": conf,
                "needs_editor_review": conf != "high"}

    # Rules only (no LLM scores): unchanged.
    passed = sum(checks.values())
    conf = "low" if hard_fail or passed <= 3 else ("high" if passed == 5 and len(rule_issues) == 0 else "medium")
    return {"checks": checks, "issues": rule_issues, "confidence": conf,
            "needs_editor_review": conf != "high"}


def post_order(ranked: list[Candidate], cfg) -> list[Candidate]:
    """Greedy posting order: best first, but spread episodes and favour early ones.

    Early-episode promos send new viewers to the start of the show (the funnel),
    spoil less, and need less backstory. Repeating the same episode back-to-back
    burns the audience, so each reuse costs a little.
    """
    r = cfg["ranking"]
    pool = list(ranked)
    order, used = [], {}
    while pool:
        def adj(c):
            ep = c.segments[-1].episode
            bonus = r["early_episode_bonus"] * max(0, (r["early_episode_cutoff"] - ep)) / r["early_episode_cutoff"]
            return c.final + bonus - r["repeat_episode_penalty"] * used.get(ep, 0)
        best = max(pool, key=adj)
        best.post_score = round(adj(best), 4)
        order.append(best)
        pool.remove(best)
        ep = best.segments[-1].episode
        used[ep] = used.get(ep, 0) + 1
    return order


def why_line(c: Candidate) -> str:
    if c.llm.get("why_it_works"):
        return c.llm["why_it_works"]
    f = c.features
    parts = []
    if c.kind == "cold_open":
        parts.append("flashes forward to the payoff, then rewinds and stops right before it")
    if f["hook"] >= 0.6:
        parts.append("opens on a high-conflict line")
    if f["cliff"] >= 0.6:
        parts.append("cuts on an unanswered threat or question" + (" at the episode's own cliffhanger" if f["finale"] else ""))
    if f["standalone"] >= 0.7:
        parts.append("relationships (sister, father, husband) are clear without backstory")
    return ("; ".join(parts) or "solid conflict but no standout hook").capitalize() + "."


def run(cfg: dict, episodes_dir: str, out_dir: str, log=print) -> dict:
    t0 = time.time()
    eps_list = load_show(episodes_dir)
    if not eps_list:
        raise ValueError(f"No screenplay .txt files found in {episodes_dir}")
    eps = {e.number: e for e in eps_list}
    log(f"Parsed {len(eps_list)} episodes ({sum(len(e.events) for e in eps_list)} events)")
    warns = [w for e in eps_list for w in e.warnings]
    if warns:
        log(f"Parse warnings ({len(warns)}), worked around, check these:")
        for w in warns:
            log(f"  WARNING {w}")

    singles = []
    for ep in eps_list:
        singles += single_candidates(ep, cfg["min_len"], cfg["max_len"])
    for c in singles:
        score_candidate(c, eps, cfg["scoring"])
    log(f"Generated + scored {len(singles)} single-stretch candidates")

    hooks_by_ep = {}
    for ep in eps_list:
        clips = [(s, ev) for s, ev in hook_clips(ep) if line_heat(ev) >= cfg["cold_open"]["min_hook_heat"]]
        hooks_by_ep[ep.number] = clips
    colds = []
    if cfg["cold_open"]["enabled"]:
        colds = cold_open_candidates(eps, singles, hooks_by_ep, cfg["min_len"], cfg["max_len"],
                                     cfg["cold_open"]["top_bodies"], cfg["cold_open"]["max_gap"])
        for c in colds:
            score_candidate(c, eps, cfg["scoring"])
        log(f"Generated + scored {len(colds)} cold-open candidates")

    all_c = singles + colds
    # Each episode's ending was written as a cliffhanger: always send its best cut to the judge.
    finales = []
    for ep in eps_list:
        fin = [c for c in singles if c.segments[0].episode == ep.number and c.features["finale"]]
        if fin:
            finales.append(max(fin, key=lambda c: c.score))
    pool = dedupe(finales, 0.99) + []
    for c in dedupe(all_c, cfg["dedupe_overlap"]):
        if all(overlap(c, k) <= cfg["dedupe_overlap"] and not same_payoff(c, k) for k in pool):
            pool.append(c)
    pool.sort(key=lambda c: c.score, reverse=True)
    k = max(cfg["shortlist_size"], int(cfg.get("shortlist_per_episode", 0) * len(eps_list)))
    rest = [c for c in pool if c not in finales][: max(0, k - len(finales))]
    shortlist = sorted(finales + rest, key=lambda c: c.score, reverse=True)
    log(f"After dedupe: {len(pool)} distinct moments; shortlist {len(shortlist)}")

    llm = LLM(cfg.get("llm", {}))
    if llm.enabled:
        log(f"LLM judge: {llm.name()}")
        judge(shortlist, eps, llm, log, version=cfg["llm"].get("judge_version", "v1"))
    set_finals(shortlist, cfg)
    final_pool = dedupe(shortlist, cfg["dedupe_overlap"], key=lambda c: c.final)[: cfg["top_n"]]
    ordered = post_order(sorted(final_pool, key=lambda c: c.final, reverse=True), cfg)

    promos = [promo_record(rank, c, eps, cfg) for rank, c in enumerate(ordered, 1)]

    meta = {
        "run_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "episodes": [e.number for e in eps_list],
        "model": llm.name(),
        "candidates_total": len(all_c), "distinct_moments": len(pool), "shortlist": len(shortlist),
        "llm_calls": llm.calls, "llm_cache_hits": llm.cache_hits,
        "tokens_in": llm.tokens_in, "tokens_out": llm.tokens_out,
        "runtime_s": round(time.time() - t0, 1),
    }
    meta["parse_warnings"] = warns
    write_outputs(promos, meta, out_dir)
    # Full shortlist (before final ranking) for audit / eval of the judge stage
    sl = [{"rules_score": c.score, "final": c.final, "type": c.kind,
           "segments": [s.to_dict() for s in c.segments],
           "features": {k: v for k, v in c.features.items() if not k.startswith("_")},
           "llm": c.llm, "transcript": transcript(c, eps)} for c in sorted(shortlist, key=lambda c: c.final, reverse=True)]
    (Path(out_dir) / "shortlist_all_scored.json").write_text(json.dumps(sl, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"Done in {meta['runtime_s']}s -> {out_dir}")
    return {"promos": promos, "meta": meta}


def promo_record(rank: int, c: Candidate, eps, cfg) -> dict:
    """One ranked promo as written to promos.json."""
    q = qa(c, eps, cfg)
    f = c.features
    return {
            "post_rank": rank,
            "promo_id": f"P{rank:02d}",
            "type": c.kind,
            "duration_s": round(c.duration, 1),
            "episodes": sorted({s.episode for s in c.segments}),
            "segments": [s.to_dict() for s in c.segments],
            "hook": c.llm.get("hook_quote") or (f'{f["hook_speaker"]}: "{f["hook_line"]}"' if f["hook_speaker"] else f["hook_line"]),
            "cliffhanger": c.llm.get("cliffhanger_quote") or (f'{f["cliff_speaker"]}: "{f["cliff_line"]}"' if f["cliff_line"] else ""),
            "why_it_works": why_line(c),
            "scores": {"final": c.final, "post_priority": c.post_score, "rules": c.score,
                       **{k: f[k] for k in ("hook", "cliff", "standalone", "heat", "length")},
                       **({"llm_" + k: c.llm[k] for k in ("hook_score", "cliffhanger_score",
                          "standalone_score", "overall") if k in c.llm})},
            "llm_weakness": c.llm.get("biggest_weakness", ""),
            "qa": q,
            "transcript": transcript(c, eps),
    }


def write_outputs(promos, meta, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "promos.json").write_text(json.dumps({"meta": meta, "promos": promos}, indent=2, ensure_ascii=False), encoding="utf-8")

    import csv
    with open(out / "promos.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["post_rank", "type", "duration_s", "segments", "hook", "cliffhanger", "why_it_works",
                    "final_score", "confidence", "issues"])
        for p in promos:
            segs = " + ".join(f"Ep{s['episode']} {s['start_tc']}-{s['end_tc']}" for s in p["segments"])
            w.writerow([p["post_rank"], p["type"], p["duration_s"], segs, p["hook"], p["cliffhanger"],
                        p["why_it_works"], p["scores"]["final"], p["qa"]["confidence"], "; ".join(p["qa"]["issues"])])

    md = [f"# Promo picks ({meta['model']})", "",
          f"Run {meta['run_at']} on episodes {meta['episodes'][0]}-{meta['episodes'][-1]}. "
          f"{meta['candidates_total']} legal cuts considered, {meta['distinct_moments']} distinct moments, "
          f"{meta['shortlist']} shortlisted. LLM calls {meta['llm_calls']} (cache hits {meta['llm_cache_hits']}). "
          f"Runtime {meta['runtime_s']}s.", ""]
    for p in promos:
        segs = " + ".join(f"Ep {s['episode']} [{s['start_tc']} → {s['end_tc']}]" for s in p["segments"])
        md += [f"## #{p['post_rank']}  {segs}  ({p['duration_s']}s, {p['type']})", "",
               f"- Hook: {p['hook']}", f"- Cliffhanger: {p['cliffhanger']}",
               f"- Why: {p['why_it_works']}",
               f"- Scores: final {p['scores']['final']}, hook {p['scores']['hook']}, cliff {p['scores']['cliff']}, "
               f"standalone {p['scores']['standalone']}" +
               (f", LLM overall {p['scores']['llm_overall']}" if "llm_overall" in p["scores"] else ""),
               f"- Confidence: {p['qa']['confidence']}" + (f" | Issues: {'; '.join(p['qa']['issues'])}" if p['qa']['issues'] else ""),
               "", "```", p["transcript"], "```", ""]
    (out / "promos.md").write_text("\n".join(md), encoding="utf-8")
    (out / "run_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

"""Re-rank a finished run from its saved scores. No LLM calls.

  python run.py --rescore-from outputs/groq_v1_final --out outputs/final

Takes the shortlist saved in <run>/shortlist_all_scored.json, recomputes the rule
scores with the current config.yaml and lexicon, keeps the saved LLM scores, and
then runs the same blend, dedupe, posting order and QA as pipeline.run(). The set
of shortlisted clips never changes, so this is safe for tuning weights after the
LLM budget is spent.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from .candidates import Candidate, Segment, hook_clips
from .features import line_heat, score_candidate, transcript
from .parser import load_show
from .pipeline import dedupe, post_order, promo_record, set_finals, write_outputs


def config_hash(cfg: dict) -> str:
    """Short, stable hash of the config that produced a run."""
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:12]


def _rebuild(entry: dict, eps) -> Candidate:
    segs = [Segment(s["episode"], s["start"], s["end"]) for s in entry["segments"]]
    c = Candidate(entry["type"], segs, llm=dict(entry.get("llm") or {}))
    if c.kind == "cold_open":
        # The saved file drops private keys, so find the hook event again from the hook segment.
        hs = segs[0]
        evs = [ev for seg, ev in hook_clips(eps[hs.episode])
               if abs(seg.start - hs.start) < 0.01 and abs(seg.end - hs.end) < 0.01]
        if evs:
            c.features["_hook_event"] = max(evs, key=line_heat)
    return c


def rescore(cfg: dict, source_run: str, episodes_dir: str, out_dir: str, tuning_notes=None, log=print) -> dict:
    t0 = time.time()
    src = Path(source_run)
    saved = json.loads((src / "shortlist_all_scored.json").read_text(encoding="utf-8"))
    src_meta = json.loads((src / "run_meta.json").read_text(encoding="utf-8"))
    eps = {e.number: e for e in load_show(episodes_dir)}
    log(f"Rescoring {len(saved)} saved clips from {src} (source model: {src_meta['model']})")

    shortlist = []
    for entry in saved:
        c = _rebuild(entry, eps)
        score_candidate(c, eps, cfg["scoring"])
        shortlist.append(c)
    set_finals(shortlist, cfg)
    final_pool = dedupe(shortlist, cfg["dedupe_overlap"], key=lambda c: c.final)[: cfg["top_n"]]
    ordered = post_order(sorted(final_pool, key=lambda c: c.final, reverse=True), cfg)
    promos = [promo_record(rank, c, eps, cfg) for rank, c in enumerate(ordered, 1)]

    end = time.strptime(src_meta["run_at"], "%Y-%m-%d %H:%M:%S")
    start = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.mktime(end) - src_meta["runtime_s"]))
    meta = {
        "run_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "episodes": sorted(eps),
        "model": src_meta["model"],
        "scores_source": {
            "note": "LLM scores are re-blended from a saved run. No LLM calls were made for this output.",
            "run_dir": str(src).replace("\\", "/"),
            "run_started": start,
            "run_finished": src_meta["run_at"],
            "llm_calls": src_meta["llm_calls"],
            "tokens_in": src_meta["tokens_in"],
            "tokens_out": src_meta["tokens_out"],
        },
        "config_hash": config_hash(cfg),
        "tuning_changes": list(tuning_notes or []),
        "candidates_total": src_meta.get("candidates_total"),
        "distinct_moments": src_meta.get("distinct_moments"),
        "shortlist": len(shortlist),
        "llm_calls": 0, "llm_cache_hits": 0, "tokens_in": 0, "tokens_out": 0,  # this re-rank itself
        "runtime_s": round(time.time() - t0, 1),
    }
    write_outputs(promos, meta, out_dir)
    sl = [{"rules_score": c.score, "final": c.final, "type": c.kind,
           "segments": [s.to_dict() for s in c.segments],
           "features": {k: v for k, v in c.features.items() if not k.startswith("_")},
           "llm": c.llm, "transcript": transcript(c, eps)}
          for c in sorted(shortlist, key=lambda c: c.final, reverse=True)]
    (Path(out_dir) / "shortlist_all_scored.json").write_text(json.dumps(sl, indent=2, ensure_ascii=False),
                                                              encoding="utf-8")
    log(f"Done in {meta['runtime_s']}s -> {out_dir}")
    return {"promos": promos, "meta": meta}

"""Grade a run against the gold set.

  python eval/evaluate.py outputs/<run>/promos.json [--gold eval/gold_promos.yaml] [--k 15]
  python eval/evaluate.py outputs/<run>/promos.json --k 5,10,15,25 --split odd

A pick "matches" a gold promo if they share at least 50% of the shorter clip's
screen time in the same episode. Reports:
  recall@k     share of gold promos the tool found in its top k
  precision@k  share of the tool's top k that are in the gold set
  misses       gold promos the tool did not find (read these: they are the failure modes)
  false alarms tool picks not in the gold set (some will be good finds, some bad picks)

Only picks from episodes the gold set covers are graded, so unlabelled episodes
never count as false alarms. --split odd|even keeps only odd or even episodes
(tune / test). The report goes to eval/reports/, never into the run folder, so
raw outputs stay exactly as the pipeline wrote them.
"""
import argparse
import json
import sys
from pathlib import Path

import yaml


def shared(seg_list, g):
    s = 0.0
    for seg in seg_list:
        if seg["episode"] == g["episode"]:
            s += max(0.0, min(seg["end"], g["end"]) - max(seg["start"], g["start"]))
    return s


def match(p, g):
    pdur = sum(s["end"] - s["start"] for s in p["segments"])
    return shared(p["segments"], g) >= 0.5 * min(pdur, g["end"] - g["start"])


def split_episodes(split, gold):
    eps = sorted({g["episode"] for g in gold})
    if split in (None, "all"):
        return None
    if split == "odd":
        return {e for e in range(1, 10_000) if e % 2 == 1}
    if split == "even":
        return {e for e in range(1, 10_000) if e % 2 == 0}
    return {int(x) for x in str(split).split(",")}


def evaluate(promos_path, gold_path, k, episodes=None, covered=None):
    """covered: episodes that were reviewed (default: the gold set's episode range).
    An episode can be reviewed and still have no gold promo; its picks then count as false alarms."""
    data = json.loads(Path(promos_path).read_text(encoding="utf-8"))
    gold = yaml.safe_load(Path(gold_path).read_text(encoding="utf-8"))
    if covered is None:
        covered = set(range(min(g["episode"] for g in gold), max(g["episode"] for g in gold) + 1))
    if episodes is not None:
        covered = covered & set(episodes)
        gold = [g for g in gold if g["episode"] in covered]
    lo, hi = min(covered), max(covered)
    keep = lambda e: e in covered  # noqa: E731
    promos = [p for p in data["promos"] if all(keep(s["episode"]) for s in p["segments"])][:k]
    found = {g["id"]: [p["post_rank"] for p in promos if match(p, g)] for g in gold}
    hits = [p for p in promos if any(match(p, g) for g in gold)]
    n_found = sum(1 for v in found.values() if v)
    recall = n_found / len(gold)
    precision = len(hits) / max(1, len(promos))
    scope = f"{len(covered)} reviewed episodes ({lo}-{hi})"
    lines = [f"# Eval: {data['meta']['model']}  ({promos_path})", "",
             f"Gold: {len(gold)} promos from {scope}; graded the top {len(promos)} picks from those episodes.", "",
             f"- recall@{k}: {recall:.0%}  ({n_found}/{len(gold)} gold promos found)",
             f"- precision@{k}: {precision:.0%}  ({len(hits)}/{len(promos)} picks match a gold promo)", "",
             "## Gold promos and where the tool ranked them"]
    for g in gold:
        r = found[g["id"]]
        lines.append(f"- {g['id']} Ep{g['episode']} {g['start']}-{g['end']}s: "
                     f"{'rank ' + ', '.join(map(str, r)) if r else 'MISSED'} | {g['why']}")
    lines += ["", "## Tool picks not in the gold set (judge each: good find or bad pick?)"]
    for p in promos:
        if p not in hits:
            segs = " + ".join(f"Ep{s['episode']} {s['start_tc']}-{s['end_tc']}" for s in p["segments"])
            lines.append(f"- #{p['post_rank']} {segs} | hook: {p['hook'][:70]} | cliff: {p['cliffhanger'][:70]}")
    report = "\n".join(lines)
    return {"recall": recall, "precision": precision, "report": report,
            "found": n_found, "gold": len(gold), "hits": len(hits), "graded": len(promos)}


if __name__ == "__main__":
    # Windows consoles default to cp1252; LLM quotes (e.g. non-breaking hyphens) would crash print().
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("promos")
    ap.add_argument("--gold", default="eval/gold_promos.yaml")
    ap.add_argument("--k", default="15", help="one k, or several: 5,10,15,25")
    ap.add_argument("--split", default="all", help="all | odd | even | comma-separated episode numbers")
    ap.add_argument("--covered", default=None, help="reviewed episodes, e.g. 1-50 (default: gold range)")
    ap.add_argument("--report-dir", default="eval/reports")
    a = ap.parse_args()
    gold_all = yaml.safe_load(Path(a.gold).read_text(encoding="utf-8"))
    eps = split_episodes(a.split, gold_all)
    cov = None
    if a.covered:
        lo_, hi_ = (int(x) for x in a.covered.split("-"))
        cov = set(range(lo_, hi_ + 1))
    ks = [int(x) for x in a.k.split(",")]
    results = {k: evaluate(a.promos, a.gold, k, eps, cov) for k in ks}
    main_k = 15 if 15 in results else ks[0]
    print(results[main_k]["report"])
    if len(ks) > 1:
        print("\n## Summary")
        for k, r in results.items():
            print(f"- recall@{k}: {r['recall']:.0%} ({r['found']}/{r['gold']})   "
                  f"precision@{k}: {r['precision']:.0%} ({r['hits']}/{r['graded']})")
    run_name = Path(a.promos).parent.name
    out_dir = Path(a.report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{run_name}_{Path(a.gold).stem}_{a.split.replace(',', '-')}.md"
    out.write_text(results[main_k]["report"], encoding="utf-8")
    print(f"\nSaved {out}")

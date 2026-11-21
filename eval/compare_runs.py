"""Compare runs on both gold sets.

  python eval/compare_runs.py . v1=outputs/final v3=outputs/final_v3

Prints recall@5/10/15/25 and precision@15 with counts, on gold (odd, even, all episodes) and gold_random
(end-to-end recall; precision only over picks that overlap one of the 60 labelled random clips).
"""
import json, os, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve(); os.chdir(root)
sys.path.insert(0, str(root / "eval"))
import yaml
from evaluate import evaluate, match

COV = set(range(1, 51)); ODD = {e for e in COV if e % 2}; EVEN = COV - ODD
R_EPS = {int(x) for x in Path("eval/random_episodes.txt").read_text().strip().split(",")}
POOL = json.load(open("eval/random_pool.json", encoding="utf-8"))
RGOLD = yaml.safe_load(open("eval/gold_random.yaml", encoding="utf-8"))
runs = [a.split("=", 1) for a in sys.argv[2:]]


def gold_cells(path):
    out = {}
    for split, eps in (("odd", ODD), ("even", EVEN), ("all", None)):
        r = {k: evaluate(path, "eval/gold_promos.yaml", k, eps, COV) for k in (5, 10, 15, 25)}
        out[split] = r
    return out


def random_cells(path):
    promos = json.load(open(path, encoding="utf-8"))["promos"]
    rec = {}
    for k in (5, 10, 15, 25):
        top = [p for p in promos if all(s["episode"] in R_EPS for s in p["segments"])][:k]
        rec[k] = sum(1 for g in RGOLD if any(match(p, g) for p in top))
    top15 = [p for p in promos if all(s["episode"] in R_EPS for s in p["segments"])][:15]
    labelled = [p for p in top15 if any(match(p, {"episode": r["segments"][-1]["episode"], "start": r["segments"][-1]["start"],
                                                    "end": r["segments"][-1]["end"]}) for r in POOL if len(r["segments"]) == 1)]
    yes = [p for p in labelled if any(match(p, g) for g in RGOLD)]
    return rec, len(yes), len(labelled)


lines = ["| Run | Gold set | R@5 | R@10 | R@15 | R@25 | P@15 |", "|---|---|---|---|---|---|---|"]
summary = {}
for name, d in runs:
    path = f"{d}/promos.json"
    g = gold_cells(path)
    summary[name] = g
    for split in ("odd", "even", "all"):
        r = g[split]; n = r[15]["gold"]
        lines.append(f"| {name} | gold {split} | " + " | ".join(f"{r[k]['found']}/{n}" for k in (5, 10, 15, 25))
                     + f" | {r[15]['hits']}/{r[15]['graded']} |")
    rec, y, lab = random_cells(path)
    lines.append(f"| {name} | gold_random | " + " | ".join(f"{rec[k]}/{len(RGOLD)}" for k in (5, 10, 15, 25))
                 + f" | {y}/{lab} labelled |")
print("\n".join(lines))

"""Cross-validated re-blend of saved scores (no LLM calls).

  python eval/cv_reblend.py [--run outputs/groq_v1_final] [--export]

Learns a small L2-regularised logistic regression on the shortlisted clips of a
finished run and compares it with the current blend (0.4 rules + 0.6 LLM) under
5-fold cross-validation with folds grouped by episode. Held-out scores from the
5 folds are stitched into one ranking of the whole pool, then the normal
pipeline tail (dedupe, top_n, posting order) turns each ranking into a promo
list that the evaluator grades. --export writes the weights trained on all
clips into config.yaml under ranking.learned_blend (switched off).
"""
import argparse
import copy
import json
import math
import random
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

from evaluate import evaluate, match  # noqa: E402
from promo_finder.parser import load_show  # noqa: E402
from promo_finder.pipeline import blended, dedupe, post_order, promo_record, write_outputs  # noqa: E402
from promo_finder.rescore import _rebuild  # noqa: E402
from promo_finder.features import score_candidate  # noqa: E402

from promo_finder.learned import FEATURES, feature_rows  # noqa: E402

WORDS = {
    "rule_hook": "rules hook score (first 3 s)",
    "rule_cliff": "rules cliffhanger score",
    "rule_standalone": "rules standalone score",
    "finale": "clip ends on the episode's last beat",
    "llm_overall": "LLM overall score",
    "llm_cliff": "LLM cliffhanger score",
    "rank_in_episode": "rank among the episode's shortlisted clips by the current blend (1 = best)",
    "llm_overall_vs_episode": "LLM overall minus the episode's average LLM overall",
}


def features(clips, cfg):
    return np.array(feature_rows(clips, lambda x: blended(x, cfg)), dtype=float)


def fit_logreg(X, y, l2=1.0, iters=50):
    """Newton / IRLS on standardised X. Returns (weights, intercept, mean, std)."""
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    A = np.hstack([np.ones((len(Z), 1)), Z])
    w = np.zeros(A.shape[1])
    reg = np.eye(A.shape[1]) * l2
    reg[0, 0] = 0.0                                   # do not shrink the intercept
    for _ in range(iters):
        p = 1 / (1 + np.exp(-A @ w))
        g = A.T @ (p - y) + reg @ w
        H = A.T @ (A * (p * (1 - p))[:, None]) + reg
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return w[1:], w[0], mu, sd


def predict(X, w, b, mu, sd):
    return 1 / (1 + np.exp(-(((X - mu) / sd) @ w + b)))


def promo_list(clips, finals, eps, cfg):
    for c, f in zip(clips, finals):
        c.final = round(float(f), 6)
    pool = dedupe(clips, cfg["dedupe_overlap"], key=lambda c: c.final)[: cfg["top_n"]]
    ordered = post_order(sorted(pool, key=lambda c: c.final, reverse=True), cfg)
    return [promo_record(r, c, eps, cfg) for r, c in enumerate(ordered, 1)]


def grade(promos, tmp, gold_all, gold_rand, rand_eps, pool_labelled):
    tmp.mkdir(parents=True, exist_ok=True)
    write_outputs(promos, {"model": "cv", "run_at": "", "episodes": [1, 50], "candidates_total": 0,
                           "distinct_moments": 0, "shortlist": 0, "llm_calls": 0, "llm_cache_hits": 0,
                           "runtime_s": 0}, str(tmp))
    p = str(tmp / "promos.json")
    out = {}
    for k in (10, 15, 25):
        r = evaluate(p, "eval/gold_promos.yaml", k, None, set(range(1, 51)))
        out[f"R@{k}"] = r["found"]
        if k == 15:
            out["P@15"] = (r["hits"], r["graded"])
    top = lambda k: [x for x in promos if all(s["episode"] in rand_eps for s in x["segments"])][:k]  # noqa: E731
    for k in (10, 15, 25):
        out[f"rand R@{k}"] = sum(1 for g in gold_rand if any(match(x, g) for x in top(k)))
    lab = [x for x in top(15) if any(match(x, g) for g in pool_labelled)]
    out["rand P@15"] = (sum(1 for x in lab if any(match(x, g) for g in gold_rand)), len(lab))
    out["_promos"] = promos
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="outputs/groq_v1_final")
    ap.add_argument("--l2", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--drop", default="", help="comma-separated features to leave out")
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--tmp", default="E:/pip_tmp/cv")
    a = ap.parse_args()

    import os
    os.chdir(ROOT)
    cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    cfg_v1 = copy.deepcopy(cfg)                       # the current blend: round-1 rules, no fixes
    for sec in ("scoring", "ranking"):
        for k in list(cfg_v1[sec]):
            if k.startswith("fix_"):
                cfg_v1[sec][k] = False
    eps = {e.number: e for e in load_show("data/episodes")}
    saved = json.loads(Path(a.run, "shortlist_all_scored.json").read_text(encoding="utf-8"))
    clips = []
    for s in saved:
        c = _rebuild(s, eps)
        score_candidate(c, eps, cfg_v1["scoring"])
        clips.append(c)
    gold = yaml.safe_load(Path("eval/gold_promos.yaml").read_text(encoding="utf-8"))
    gold_rand = yaml.safe_load(Path("eval/gold_random.yaml").read_text(encoding="utf-8"))
    pool_rand = json.loads(Path("eval/random_pool.json").read_text(encoding="utf-8"))
    pool_labelled = [{"episode": r["segments"][-1]["episode"], "start": r["segments"][-1]["start"],
                      "end": r["segments"][-1]["end"]} for r in pool_rand if len(r["segments"]) == 1]
    rand_eps = {r["segments"][-1]["episode"] for r in pool_rand}
    labels = gold + gold_rand
    y = np.array([1.0 if any(match({"segments": [s.to_dict() for s in c.segments]}, g) for g in labels) else 0.0
                  for c in clips])

    keep = [i for i, f in enumerate(FEATURES) if f not in a.drop.split(",")]
    names = [FEATURES[i] for i in keep]
    X = features(clips, cfg_v1)[:, keep]

    episodes = sorted({c.segments[-1].episode for c in clips})
    rng = random.Random(a.seed)
    rng.shuffle(episodes)
    folds = [set(episodes[i::5]) for i in range(5)]
    ep_of = np.array([c.segments[-1].episode for c in clips])

    held = np.zeros(len(clips))
    for f in folds:
        test = np.isin(ep_of, list(f))
        w, b, mu, sd = fit_logreg(X[~test], y[~test], a.l2)
        held[test] = predict(X[test], w, b, mu, sd)

    base = np.array([blended(c, cfg_v1) for c in clips])
    res_base = grade(promo_list(clips, base, eps, cfg_v1), Path(a.tmp) / "base", gold, gold_rand, rand_eps, pool_labelled)
    res_cv = grade(promo_list(clips, held, eps, cfg_v1), Path(a.tmp) / "cv", gold, gold_rand, rand_eps, pool_labelled)

    # Per fold: gold hits (31-clip set) inside the top 15 of each list that come from that fold's episodes.
    def fold_hits(promos, f):
        top = [p for p in promos[:15] if p["segments"][-1]["episode"] in f]
        return sum(1 for p in top if any(match(p, g) for g in gold))

    per_fold = [(fold_hits(res_base["_promos"], f), fold_hits(res_cv["_promos"], f)) for f in folds]

    # Per fold average precision of the held-out ranking against all labels (pure ranking quality).
    def ap_score(scores, idx):
        order = sorted(idx, key=lambda i: -scores[i])
        hits, s = 0, 0.0
        for r, i in enumerate(order, 1):
            if y[i]:
                hits += 1
                s += hits / r
        return s / max(1, hits)

    aps = [(ap_score(base, np.where(np.isin(ep_of, list(f)))[0]), ap_score(held, np.where(np.isin(ep_of, list(f)))[0]))
           for f in folds]

    gain15 = res_cv["R@15"] - res_base["R@15"]
    p_ok = res_cv["P@15"][0] * res_base["P@15"][1] >= res_base["P@15"][0] * res_cv["P@15"][1]
    folds_won = sum(1 for b_, c_ in per_fold if c_ > b_)
    accept = gain15 >= 2 and p_ok and folds_won >= 3

    w, b, mu, sd = fit_logreg(X, y, a.l2)
    print(f"Clips {len(clips)}, positives {int(y.sum())}, features {len(names)}, L2 {a.l2}, fold seed {a.seed}")
    print("\n| Metric | Current blend | CV re-blend |\n|---|---|---|")
    for k in ("R@10", "R@15", "R@25"):
        print(f"| gold {k} | {res_base[k]}/31 | {res_cv[k]}/31 |")
    print(f"| gold P@15 | {res_base['P@15'][0]}/{res_base['P@15'][1]} | {res_cv['P@15'][0]}/{res_cv['P@15'][1]} |")
    for k in ("rand R@10", "rand R@15", "rand R@25"):
        print(f"| gold_random {k[5:]} | {res_base[k]}/{len(gold_rand)} | {res_cv[k]}/{len(gold_rand)} |")
    print(f"| gold_random P@15 (labelled picks) | {res_base['rand P@15'][0]}/{res_base['rand P@15'][1]} | "
          f"{res_cv['rand P@15'][0]}/{res_cv['rand P@15'][1]} |")
    print("\n| Fold | Episodes | Gold hits in top 15, current | Gold hits in top 15, CV | Avg precision current | Avg precision CV |")
    print("|---|---|---|---|---|---|")
    for i, (f, (hb, hc), (ab, ac)) in enumerate(zip(folds, per_fold, aps), 1):
        print(f"| {i} | {','.join(map(str, sorted(f)))} | {hb} | {hc} | {ab:.2f} | {ac:.2f} |")
    print(f"\nAccept rule: R@15 gain {gain15:+d} (need >= +2), precision not worse: {p_ok}, "
          f"folds won {folds_won}/5 (need >= 3)  ->  {'ACCEPT' if accept else 'NO GAIN'}")
    print("\nWeights trained on all 120 clips (standardised features; positive = more likely a good promo):")
    for n, wi in sorted(zip(names, w), key=lambda t: -abs(t[1])):
        print(f"  {wi:+.2f}  {WORDS[n]}")
    if a.export:
        p = Path("config.yaml")
        s = p.read_text(encoding="utf-8")
        block = {"enabled": False, "accepted_by_cv": bool(accept), "features": names,
                 "weights": [round(float(x), 4) for x in w], "intercept": round(float(b), 4),
                 "mean": [round(float(x), 4) for x in mu], "std": [round(float(x), 4) for x in sd],
                 "note": "logistic re-blend learned by eval/cv_reblend.py; final = sigmoid(w . (x - mean) / std + b)"}
        text = "  learned_blend:\n" + "".join(f"    {k}: {json.dumps(v)}\n" for k, v in block.items())
        start = s.find("  learned_blend:\n")
        if start >= 0:
            end = s.find("\n\n", start)
            s = s[:start] + text.rstrip("\n") + s[end:]
        else:
            s = s.replace("  resolved_llm_cliff_max: 6\n", "  resolved_llm_cliff_max: 6\n" + text)
        p.write_text(s, encoding="utf-8")
        print("\nExported to config.yaml ranking.learned_blend (enabled: false)")


if __name__ == "__main__":
    main()

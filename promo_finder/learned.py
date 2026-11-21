"""Optional learned re-blend (ranking.learned_blend in config.yaml, off by default).

A logistic regression over 8 explainable features of a judged shortlist. The
weights come from eval/cv_reblend.py --export. Cross-validation did NOT show a
gain over the current blend (DECISIONS.md D45), so the switch stays off.
"""
from __future__ import annotations

import math

FEATURES = ["rule_hook", "rule_cliff", "rule_standalone", "finale", "llm_overall", "llm_cliff",
            "rank_in_episode", "llm_overall_vs_episode"]


def feature_rows(clips, blend) -> list[list[float]]:
    """One row per clip. blend(c) is the current score, used for the within-episode rank."""
    by_ep = {}
    for c in clips:
        by_ep.setdefault(c.segments[-1].episode, []).append(c)
    rows = []
    for c in clips:
        ep = by_ep[c.segments[-1].episode]
        order = sorted(ep, key=blend, reverse=True)
        judged = [x for x in ep if "overall" in x.llm]
        ep_mean = sum(x.llm["overall"] for x in judged) / len(judged) if judged else 0.0
        f, l = c.features, c.llm
        rows.append([f["hook"], f["cliff"], f["standalone"], 1.0 if f["finale"] else 0.0,
                     l.get("overall", 0) / 10, l.get("cliffhanger_score", 0) / 10,
                     float(order.index(c) + 1), (l.get("overall", 0) - ep_mean) / 10])
    return rows


def learned_finals(clips, blend, lb: dict) -> list[float]:
    idx = [FEATURES.index(n) for n in lb["features"]]
    out = []
    for row in feature_rows(clips, blend):
        z = sum(w * (row[i] - m) / (s or 1.0) for w, i, m, s in zip(lb["weights"], idx, lb["mean"], lb["std"]))
        out.append(1 / (1 + math.exp(-(z + lb["intercept"]))))
    return out

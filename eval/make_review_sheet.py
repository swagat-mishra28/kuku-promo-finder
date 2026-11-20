"""Build a blind labelling sheet for the editor gold set.

  python eval/make_review_sheet.py [--run outputs/groq_v1_final] [--out eval/review_sheet.md] [--seed 7]

Per episode: its top 3 shortlisted clips by final score, plus 2 random legal cuts that
the system did not put in that top 3 ("extra"), so misses can be caught too.
The sheet shows no scores and no model reasoning, and lists clips by start time,
not by rank, so the labeller is not anchored by the model.

The sheet quotes screenplay text: it is git-ignored and must never be committed.
"""
import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from promo_finder.candidates import Candidate, Segment, single_candidates, tc  # noqa: E402
from promo_finder.features import transcript  # noqa: E402
from promo_finder.parser import load_show  # noqa: E402
from promo_finder.pipeline import overlap, same_payoff  # noqa: E402

HEADER = """# Promo review sheet (blind)

**Your task:** across all 50 episodes, mark **25 to 35 clips YES** in total. For each YES,
write one line in your own words on why it works as a paid promo. NO and MAYBE need no reason.

A YES clip:
- stops a scrolling stranger in the first 3 seconds,
- cuts on something unresolved, so they would tap through to see what happens,
- makes sense to someone who has never seen the show.

How to read a row:
- Clips are listed by start time inside each episode. The order says nothing about quality.
- Some clips are marked **extra**: random cuts the tool did not put in its top 3 for that episode.
  Judge them the same way. A YES on an extra shows something the tool missed.
- Timestamps in the heading are from the start of the episode. Timestamps inside the
  transcript are seconds from the start of the clip.
- A "cold open" plays a short flash from later first, then the build-up.

When you're done, say so and Claude can turn your YES rows into `eval/gold_promos.yaml` entries
for you to check (Claude never adds labels on its own).

This file quotes the screenplays. It is git-ignored: never commit or share it.
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="outputs/groq_v1_final")
    ap.add_argument("--out", default="eval/review_sheet.md")
    ap.add_argument("--episodes", default="data/episodes")
    ap.add_argument("--per_episode", type=int, default=3)
    ap.add_argument("--extras", type=int, default=2)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    eps_list = load_show(str(ROOT / a.episodes))
    eps = {e.number: e for e in eps_list}
    shortlist = json.loads((ROOT / a.run / "shortlist_all_scored.json").read_text(encoding="utf-8"))
    rng = random.Random(a.seed)
    max_ov = cfg["dedupe_overlap"]

    def to_cand(entry):
        return Candidate(kind=entry["type"],
                         segments=[Segment(s["episode"], s["start"], s["end"]) for s in entry["segments"]])

    rows = []  # (episode, candidate, is_extra, transcript_text)
    counts = {"top": 0, "extra": 0}
    for ep in eps_list:
        mine = [s for s in shortlist if s["segments"][-1]["episode"] == ep.number]
        top = sorted(mine, key=lambda s: s["final"], reverse=True)[: a.per_episode]
        listed = [to_cand(s) for s in top]
        for s, c in zip(top, listed):
            rows.append((ep.number, c, False, s["transcript"]))
        pool = single_candidates(ep, cfg["min_len"], cfg["max_len"])
        rng.shuffle(pool)
        # Prefer extras far from the listed clips; short episodes have no room, so relax the
        # overlap limit step by step. An extra must never end on the same beat as another row.
        extras = []
        for limit in (max_ov, 0.5, 0.65, 0.8):
            for c in pool:
                if len(extras) == a.extras:
                    break
                if c not in extras and all(overlap(c, k) <= limit and not same_payoff(c, k)
                                           for k in listed + extras):
                    extras.append(c)
        for c in extras:
            rows.append((ep.number, c, True, transcript(c, eps)))
        counts["top"] += len(listed)
        counts["extra"] += len(extras)

    md = [HEADER, f"{len(rows)} clips: {counts['top']} from the tool's per-episode top {a.per_episode} "
                  f"and {counts['extra']} extras (seed {a.seed}).", ""]
    for ep in eps_list:
        ep_rows = sorted([r for r in rows if r[0] == ep.number], key=lambda r: r[1].segments[0].start)
        md += [f"## Episode {ep.number}", ""]
        for i, (_, c, is_extra, text) in enumerate(ep_rows, 1):
            cid = f"E{ep.number:02d}-{i}"
            segs = " + ".join(f"{tc(s.start)}–{tc(s.end)}" for s in c.segments)
            tags = [t for t in ("cold open" if c.kind == "cold_open" else "", "extra" if is_extra else "") if t]
            md += [f"### {cid} · Ep {ep.number} · {segs} · {c.duration:.1f} s" + (f" · {', '.join(tags)}" if tags else ""),
                   "", "**YES / NO / MAYBE:** ", "", "**My why:** ", "", "```", text, "```", ""]
    out = ROOT / a.out
    out.write_text("\n".join(md), encoding="utf-8")
    print(f"Wrote {out} ({len(rows)} clips: {counts['top']} top, {counts['extra']} extra)")


if __name__ == "__main__":
    main()

"""Build a sheet for checking the AI-drafted gold labels, one clip at a time.

  python eval/make_gold_review.py [--out eval/gold_review_sheet.md] [--context 10]

For every entry in eval/gold_promos.yaml and eval/gold_random.yaml it shows the AI's reason,
the clip's lines with episode timestamps, and a few seconds before and after the clip so the
start and end can be moved. A clip that is in both files is shown once.

The sheet quotes screenplay text: it is git-ignored and must never be committed.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from promo_finder.candidates import tc  # noqa: E402
from promo_finder.parser import load_show  # noqa: E402

HEADER = """# Gold label review

The gold labels below were drafted by AI (Claude) from the transcripts. Every score in the
report is measured against them, so they need your judgement before you submit.

**For each clip, fill in one decision:**
- **KEEP**: a good paid promo, and the start and end are right.
- **CHANGE**: a good promo, but move the start or end. Write the new times in episode seconds
  (the numbers in square brackets), e.g. `start 12.5, end 48.0`. A clip must be 20 to 60 s.
- **DROP**: not a promo you would pay to post.

A good promo stops a scrolling stranger in the first 3 seconds, cuts on something unresolved,
and makes sense to someone who has never seen the show. Rewrite the reason in your own words
if the AI's one is wrong or weak; leave it blank to keep the AI's.

How to read the transcript: `[  23.4]` is seconds from the start of the episode. Lines marked
`before` and `after` are outside the clip and shown only so you can move its edges.
Camera directions are left out.

At the end there is space for clips the AI missed. When you're done, tell Claude: it will
update the label files from your decisions, re-run the eval and update the report numbers.
Only your decisions are applied.

This file quotes the screenplays. It is git-ignored: never commit or share it.
"""


def load(path):
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8")) or []


def excerpt(ep, start, end, ctx):
    rows = []
    for e in ep.events:
        if e.kind == "camera" or e.end < start - ctx or e.start > end + ctx:
            continue
        where = "before" if e.end <= start + 0.05 else "after " if e.start >= end - 0.05 else "      "
        if e.kind == "dialogue":
            body = f"{e.speaker}{' (O.S.)' if e.offscreen else ''}{f' ({e.tone})' if e.tone else ''}: \"{e.text}\""
        else:
            body = f"{e.kind.upper()}: {e.text}"
        rows.append(f"{where} [{e.start:6.1f}] {body}")
    return "\n".join(rows) or "(no lines found in this range: check the times)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="eval/gold_review_sheet.md")
    ap.add_argument("--episodes", default="data/episodes")
    ap.add_argument("--context", type=float, default=10.0, help="seconds shown before and after each clip")
    a = ap.parse_args()

    eps = {e.number: e for e in load_show(ROOT / a.episodes)}
    main_set, random_set = load("eval/gold_promos.yaml"), load("eval/gold_random.yaml")
    key = lambda g: (g["episode"], round(float(g["start"]), 2), round(float(g["end"]), 2))  # noqa: E731
    in_main = {key(g): g["id"] for g in main_set}

    md = [HEADER]
    problems = []

    def block(g, also=""):
        ep = eps.get(g["episode"])
        s, e = float(g["start"]), float(g["end"])
        head = f"### {g['id']} · Ep {g['episode']} · {tc(s)}–{tc(e)} ({s:g}–{e:g} s) · {e - s:.1f} s"
        if also:
            head += f" · also {also}"
        out = [head, "", f"**AI's reason:** {g.get('why', '')}", "",
               "**Decision (KEEP / CHANGE / DROP):** ", "", "**New times (only for CHANGE):** ", "",
               "**My reason (optional):** ", ""]
        if ep is None:
            problems.append(f"{g['id']}: episode {g['episode']} not found")
            return out + ["(episode not found in data/episodes)", ""]
        if ep.logline:
            out += [f"*Episode {ep.number}: {ep.logline}*", ""]
        return out + ["```", excerpt(ep, s, e, a.context), "```", ""]

    md += [f"## Main gold set ({len(main_set)} clips, eval/gold_promos.yaml)", "",
           "Used for recall@k and precision@15 in the report's results table.", ""]
    for g in main_set:
        twin = [r["id"] for r in random_set if key(r) == key(g)]
        md += block(g, also=", ".join(twin))

    extra = [r for r in random_set if key(r) not in in_main]
    shared = len(random_set) - len(extra)
    md += [f"## Random gold set ({len(random_set)} clips, eval/gold_random.yaml)", "",
           f"{shared} of these are the same clip as one above: your decision there applies to both. "
           f"The other {len(extra)} are below. This set backs the report's line "
           "\"5 of 13 at recall@15\".", ""]
    for g in extra:
        md += block(g)

    md += ["## Clips the AI missed (optional)", "",
           "One line each: episode, start and end in seconds, and why. Format: `Ep <n>, <start>–<end>, <why it works>`.", "", "- ", "- ", "- ", ""]

    out = ROOT / a.out
    out.write_text("\n".join(md), encoding="utf-8")
    print(f"Wrote {out}: {len(main_set)} main + {len(extra)} random-only clips ({shared} shared)")
    for p in problems:
        print("WARNING", p)


if __name__ == "__main__":
    main()

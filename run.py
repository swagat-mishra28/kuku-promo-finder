"""CLI.

  python run.py                                   # rules only, free, offline
  python run.py --provider gemini --model gemini-2.5-flash
  python run.py --episodes path/to/new_show --out outputs/new_show
  python run.py --rescore-from outputs/groq_v1_final --out outputs/final   # re-rank saved scores, no LLM
"""
import argparse
import os
import sys
import time
from pathlib import Path

import yaml

from promo_finder.pipeline import run
from promo_finder.rescore import rescore


def main():
    # Windows consoles default to cp1252; LLM text (e.g. non-breaking hyphens) would crash print().
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Find promo clips in microdrama screenplays")
    ap.add_argument("--episodes", default="data/episodes")
    ap.add_argument("--out", default=None)
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--provider", default=None, help="override llm.provider (none to disable)")
    ap.add_argument("--model", default=None)
    ap.add_argument("--top", type=int, default=None)
    ap.add_argument("--rescore-from", default=None, metavar="RUN_DIR",
                    help="re-rank a finished run from its saved scores (no LLM calls)")
    ap.add_argument("--rejudge-from", default=None, metavar="RUN_DIR",
                    help="judge the SAME saved shortlist again with the configured model and prompt")
    a = ap.parse_args()

    cfg = yaml.safe_load(Path(a.config).read_text(encoding="utf-8"))
    # Command-line choices beat .env. llm.py reads env vars before config, so set both.
    if a.provider:
        cfg["llm"]["provider"] = a.provider
        os.environ["PROMO_LLM_PROVIDER"] = a.provider
    if a.model:
        cfg["llm"]["model"] = a.model
        os.environ["PROMO_LLM_MODEL"] = a.model
    if a.top:
        cfg["top_n"] = a.top
    if a.rejudge_from:
        from promo_finder.llm import LLM
        llm = LLM(cfg["llm"])
        if not llm.enabled:
            raise SystemExit("--rejudge-from needs a provider (set --provider or PROMO_LLM_PROVIDER)")
        out = a.out or f"outputs/{time.strftime('%Y%m%d_%H%M')}_rejudged"
        rescore(cfg, a.rejudge_from, a.episodes, out, tuning_notes=cfg.get("tuning_log", []), llm=llm)
        return
    if a.rescore_from:
        os.environ["PROMO_LLM_PROVIDER"] = "none"   # belt and braces: rescoring never calls a model
        out = a.out or f"outputs/{time.strftime('%Y%m%d_%H%M')}_rescored"
        rescore(cfg, a.rescore_from, a.episodes, out, tuning_notes=cfg.get("tuning_log", []))
        return
    tag = cfg["llm"]["provider"] if cfg["llm"]["provider"] != "none" else "rules"
    out = a.out or f"outputs/{time.strftime('%Y%m%d_%H%M')}_{tag}"
    run(cfg, a.episodes, out)


if __name__ == "__main__":
    main()

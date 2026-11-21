"""Streamlit UI: upload screenplays (or use the invented sample), get a ranked promo sheet.

  streamlit run app.py

Rules-only mode is the default and needs no key. A visitor can paste their own key for a
model run; it is used for that run only and never written to disk or to the environment.
Uploads are parsed from memory: nothing is written to disk and the LLM cache is off.
"""
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from promo_finder.llm import load_dotenv
from promo_finder.pipeline import promos_csv, run
from promo_finder.uploads import read_uploads

ROOT = Path(__file__).resolve().parent
SAMPLE_DIR = ROOT / "data" / "sample"

st.set_page_config(page_title="Promo Finder", layout="wide")
st.title("Promo Finder for microdrama screenplays")
st.caption("Finds 20 to 60 second promo clips that open on a hook, end on a cliffhanger, "
           "and make sense to someone who has never seen the show.")

cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
load_dotenv()   # local runs only; the cloud app has no .env


def secret(name: str) -> str:
    """Streamlit secrets first (cloud), then .env (local). Never the sidebar."""
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # noqa: BLE001  no secrets file is normal
        pass
    return os.getenv(name, "")


PROVIDERS = ["none", "groq", "gemini", "openrouter", "openai", "anthropic", "openai_compatible"]

with st.sidebar:
    st.header("Input")
    source = st.radio("Screenplays", ["Use the sample show (4 invented episodes)", "Upload my own"])
    files = []
    if source == "Upload my own":
        files = st.file_uploader("One .txt per episode, or a .zip of them. Many files are fine.",
                                 type=["txt", "zip"], accept_multiple_files=True)
    st.caption("Uploaded files are processed in memory and not stored.")

    st.header("Model")
    provider = st.selectbox("Provider", PROVIDERS, index=0,
                            help="'none' is the free rules-only mode: no API calls, no key needed.")
    model, base_url, api_key = "", "", ""
    if provider != "none":
        model = st.text_input("Model", value=cfg["llm"]["model"] if provider == "groq" else "")
        if provider == "openai_compatible":
            base_url = st.text_input("Base URL", placeholder="https://your-api.example.com/v1")
        api_key = st.text_input("Your API key", type="password",
                                help="Used for this run only. It is not saved anywhere.")
        api_key = api_key or secret("PROMO_LLM_API_KEY")
        if not api_key:
            st.warning("Paste an API key, or pick 'none' for rules-only mode.")
        elif provider == "groq":
            st.caption("Free Groq keys are rate limited: expect about 13 s per judged clip.")

    st.header("Settings")
    top_n = st.slider("Promos to return", 5, 30, cfg["top_n"])
    per_ep = st.slider("Clips per episode sent to the model", 1.0, 4.0, float(cfg["shortlist_per_episode"]), 0.2)
    cold = st.checkbox("Allow cold-open (two-segment) promos", value=cfg["cold_open"]["enabled"])
    ready = source != "Upload my own" or bool(files)
    go = st.button("Find promos", type="primary", disabled=not ready or (provider != "none" and not api_key))

if go:
    if source == "Upload my own":
        items, notes = read_uploads(files)
    else:
        items = [(p.name, p.read_bytes()) for p in sorted(SAMPLE_DIR.glob("*.txt"))]
        notes = []
    cfg["top_n"], cfg["shortlist_per_episode"] = top_n, per_ep
    cfg["cold_open"]["enabled"] = cold
    cfg["llm"].update(provider=provider, model=model, base_url=base_url, api_key=api_key,
                      from_env=False, cache=False)
    st.session_state.pop("res", None)
    if not items:
        st.error("No .txt screenplays found in the upload." + (" " + "; ".join(notes) if notes else ""))
    else:
        log_box = st.empty()
        logs = []

        def log(msg):
            logs.append(msg)
            log_box.code("\n".join(logs[-14:]))

        try:
            with st.spinner(f"Working on {len(items)} file(s)..."):
                res = run(cfg, items, None, log=log)
            res["meta"]["parse_warnings"] = notes + res["meta"].get("parse_warnings", [])
            st.session_state["res"] = res
            log_box.empty()
        except Exception as e:  # noqa: BLE001  show the reason instead of a stack trace
            st.error(f"The run stopped: {e}")

res = st.session_state.get("res")
if res:
    m, promos = res["meta"], res["promos"]
    if m.get("parse_warnings"):
        with st.expander(f"⚠️ {len(m['parse_warnings'])} input warning(s), worked around", expanded=True):
            for w in m["parse_warnings"]:
                st.write("- " + w)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Episodes", len(m["episodes"]))
    c2.metric("Legal cuts scored", f"{m['candidates_total']:,}")
    c3.metric("Model calls", m["llm_calls"])
    c4.metric("Runtime", f"{m['runtime_s']} s")
    conf = {k: sum(p["qa"]["confidence"] == k for p in promos) for k in ("high", "medium", "low")}
    st.caption(f"Model: {m['model']}. Confidence: {conf['high']} high, {conf['medium']} medium, {conf['low']} low.")

    st.info(
        "**How to read this.** Rows are in posting order: the strongest clips first, spread across episodes, "
        "early episodes slightly favoured so a new viewer can start the show. Each clip is one stretch of an "
        "episode, or a cold open (a 2 to 6 second flash of the payoff, then the build-up that stops just before it). "
        "Hook is the line in the first 3 seconds; cliffhanger is the last beat. Confidence: 🟢 high means every "
        "check passed; 🟡 medium and 🔴 low list what an editor should check before posting. "
        "In rules-only mode the scores come from code alone; a model run re-scores the shortlist.")

    rows = [{"#": p["post_rank"],
             "segments": " + ".join(f"Ep{s['episode']} {s['start_tc']}-{s['end_tc']}" for s in p["segments"]),
             "sec": p["duration_s"], "type": p["type"], "hook": p["hook"], "cliffhanger": p["cliffhanger"],
             "score": p["scores"]["final"], "confidence": p["qa"]["confidence"],
             "check": "; ".join(p["qa"]["issues"])} for p in promos]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    for p in promos:
        segs = " + ".join(f"Ep {s['episode']} [{s['start_tc']} to {s['end_tc']}]" for s in p["segments"])
        badge = {"high": "🟢", "medium": "🟡", "low": "🔴"}[p["qa"]["confidence"]]
        with st.expander(f"{badge} #{p['post_rank']}  {segs}  · {p['duration_s']}s · {p['type']}"):
            st.markdown(f"**Hook:** {p['hook']}  \n**Cliffhanger:** {p['cliffhanger']}  \n**Why:** {p['why_it_works']}")
            if p["qa"]["issues"]:
                st.warning("Check: " + "; ".join(p["qa"]["issues"]))
            st.json(p["scores"], expanded=False)
            st.code(p["transcript"], language=None)

    c1, c2 = st.columns(2)
    c1.download_button("Download promos.csv", promos_csv(promos), "promos.csv", "text/csv")
    c2.download_button("Download promos.json", json.dumps(res, indent=2, ensure_ascii=False),
                       "promos.json", "application/json")
else:
    st.info("Pick the sample show or upload screenplays, then press **Find promos**. "
            "Provider 'none' is free and needs no key.")

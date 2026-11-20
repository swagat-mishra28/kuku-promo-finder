"""Streamlit UI: upload screenplays, pick a model (or none), get a ranked promo sheet.

  streamlit run app.py

No screenplays ship with the app. Upload .txt files or one .zip of them.
The API key comes from Streamlit secrets, then .env, then the sidebar box.
Provider "none" is a free rules-only mode that needs no key.
"""
import io
import json
import os
import shutil
import tempfile
import time
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from promo_finder.llm import load_dotenv
from promo_finder.pipeline import run

st.set_page_config(page_title="Promo Finder", layout="wide")
st.title("Promo Finder for microdrama screenplays")
st.caption("Finds 20-60 s promo clips that open on a hook, end on a cliffhanger, and make sense to a stranger.")

cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
load_dotenv()


def secret(name: str) -> str:
    """Streamlit secrets first (cloud), then environment / .env (local)."""
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # noqa: BLE001  no secrets file locally is normal
        pass
    return os.getenv(name, "")


PROVIDERS = ["none", "groq", "gemini", "openrouter", "openai", "anthropic", "openai_compatible", "ollama"]
default_provider = secret("PROMO_LLM_PROVIDER") or "none"
stored_key = secret("PROMO_LLM_API_KEY")

with st.sidebar:
    st.header("Input")
    files = st.file_uploader("Screenplays: .txt files (one per episode) or one .zip",
                             type=["txt", "zip"], accept_multiple_files=True)
    st.header("Model")
    provider = st.selectbox("Provider", PROVIDERS,
                            index=PROVIDERS.index(default_provider) if default_provider in PROVIDERS else 0,
                            help="'none' = free rules-only mode, no API calls, no key needed")
    model = st.text_input("Model", value=secret("PROMO_LLM_MODEL") or cfg["llm"]["model"])
    base_url = st.text_input("Base URL (openai_compatible only)", value=secret("PROMO_LLM_BASE_URL"))
    typed_key = st.text_input("API key", type="password", value="",
                              help="Leave empty to use the key from secrets or .env" if stored_key else None)
    if provider != "none" and not (typed_key or stored_key):
        st.warning("No API key found. Add one, or pick 'none' for rules-only mode.")
    st.header("Settings")
    top_n = st.slider("Promos to return", 5, 30, cfg["top_n"])
    per_ep = st.slider("Clips per episode sent to the LLM", 1.0, 4.0, float(cfg["shortlist_per_episode"]), 0.2)
    cold = st.checkbox("Allow cold-open (two-segment) promos", value=cfg["cold_open"]["enabled"])
    go = st.button("Find promos", type="primary", disabled=not files)


def unpack(uploads, dest: Path) -> int:
    n = 0
    for f in uploads:
        if f.name.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(f.getvalue())) as z:
                for info in z.infolist():
                    name = Path(info.filename).name
                    if name.lower().endswith(".txt") and not name.startswith(("._", ".")):
                        (dest / name).write_bytes(z.read(info))
                        n += 1
        else:
            (dest / Path(f.name).name).write_bytes(f.getvalue())
            n += 1
    return n


if go:
    cfg["top_n"], cfg["shortlist_per_episode"] = top_n, per_ep
    cfg["cold_open"]["enabled"] = cold
    cfg["llm"].update(provider=provider, model=model, base_url=base_url)
    # The sidebar choice must beat .env and secrets: llm.py reads these env vars first.
    os.environ["PROMO_LLM_PROVIDER"] = provider
    os.environ["PROMO_LLM_MODEL"] = model
    os.environ["PROMO_LLM_BASE_URL"] = base_url
    if typed_key or stored_key:
        os.environ["PROMO_LLM_API_KEY"] = typed_key or stored_key
    tmp = Path(tempfile.mkdtemp())
    out_dir = Path(tempfile.gettempdir()) / f"promo_finder_{time.strftime('%Y%m%d_%H%M%S')}"
    try:
        n = unpack(files, tmp)
        if n == 0:
            st.error("No .txt screenplays found in the upload.")
            st.stop()
        log_box = st.empty()
        logs = []

        def log(msg):
            logs.append(msg)
            log_box.code("\n".join(logs[-14:]))

        with st.spinner(f"Working on {n} file(s)..."):
            res = run(cfg, str(tmp), str(out_dir), log=log)
        st.session_state["res"] = res
        st.session_state["csv"] = (out_dir / "promos.csv").read_bytes()
    except ValueError as e:
        st.error(str(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

res = st.session_state.get("res")
if res:
    m = res["meta"]
    if m.get("parse_warnings"):
        with st.expander(f"⚠️ {len(m['parse_warnings'])} parse warning(s), worked around", expanded=True):
            for w in m["parse_warnings"]:
                st.write("- " + w)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Episodes", len(m["episodes"]))
    c2.metric("Legal cuts scored", f"{m['candidates_total']:,}")
    c3.metric("LLM calls", m["llm_calls"])
    c4.metric("Runtime", f"{m['runtime_s']} s")
    st.caption(f"Model: {m['model']}")

    rows = [{"#": p["post_rank"],
             "segments": " + ".join(f"Ep{s['episode']} {s['start_tc']}-{s['end_tc']}" for s in p["segments"]),
             "sec": p["duration_s"], "type": p["type"], "hook": p["hook"], "cliffhanger": p["cliffhanger"],
             "score": p["scores"]["final"], "confidence": p["qa"]["confidence"]} for p in res["promos"]]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    for p in res["promos"]:
        segs = " + ".join(f"Ep {s['episode']} [{s['start_tc']} to {s['end_tc']}]" for s in p["segments"])
        badge = {"high": "🟢", "medium": "🟡", "low": "🔴"}[p["qa"]["confidence"]]
        with st.expander(f"{badge} #{p['post_rank']}  {segs}  · {p['duration_s']}s · {p['type']}"):
            st.markdown(f"**Hook:** {p['hook']}  \n**Cliffhanger:** {p['cliffhanger']}  \n**Why:** {p['why_it_works']}")
            if p["qa"]["issues"]:
                st.warning("Check: " + "; ".join(p["qa"]["issues"]))
            st.json(p["scores"], expanded=False)
            st.code(p["transcript"], language=None)

    st.download_button("Download promos.json", json.dumps(res, indent=2, ensure_ascii=False),
                       "promos.json", "application/json")
    st.download_button("Download promos.csv", st.session_state["csv"], "promos.csv", "text/csv")
else:
    st.info("Upload screenplays (.txt files or a .zip) and press **Find promos**. "
            "Provider 'none' runs free and offline.")

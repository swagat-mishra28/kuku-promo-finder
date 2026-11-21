"""Streamlit UI: upload screenplays (or use the invented sample), get a ranked promo sheet.

  streamlit run app.py

Rules-only mode is the default and needs no key. A visitor can paste their own key for a
model run; it is used for that run only and never written to disk or to the environment.
Uploads are parsed from memory: nothing is written to disk and the LLM cache is off.
"""
import html
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from promo_finder.llm import load_dotenv
from promo_finder.parser import load_show
from promo_finder.pipeline import promos_csv, run
from promo_finder.uploads import read_uploads

ROOT = Path(__file__).resolve().parent
SAMPLE_DIR = ROOT / "data" / "sample"
PROVIDERS = ["none", "groq", "gemini", "openrouter", "openai", "anthropic", "openai_compatible"]
CONF = {"high": ("High confidence", "c-high"), "medium": ("Check before posting", "c-med"),
        "low": ("Needs an editor", "c-low")}
# QA check names, as an editor would read them. The CSV and JSON keep the raw names.
CHECK_TEXT = {"length_20_60s": "length is 20 to 60 s", "no_line_cut_mid_sentence": "no line is cut mid-sentence",
              "hook_in_first_3s": "strong hook in the first 3 s", "ends_unresolved": "ends on an unresolved beat",
              "understandable_cold": "makes sense to a new viewer"}
ISSUE_TEXT = {"length_20_60s": "length is outside 20 to 60 s", "no_line_cut_mid_sentence": "a cut lands mid-line",
              "hook_in_first_3s": "weak hook in the first 3 s", "ends_unresolved": "the ending may feel resolved",
              "understandable_cold": "may be hard to follow for a new viewer"}

st.set_page_config(page_title="Promo Finder", page_icon="🎬", layout="wide")

CSS = """
<style>
.block-container {padding-top: 3.6rem; max-width: 1180px;}
h1, h2, h3 {letter-spacing: -0.01em;}
.hero {padding: 26px 30px; border-radius: 18px; margin-bottom: 18px;
  background: radial-gradient(1200px 300px at 0% 0%, rgba(255,77,109,.22), transparent 60%),
              radial-gradient(900px 300px at 100% 100%, rgba(124,92,255,.20), transparent 60%), #13141B;
  border: 1px solid #252734;}
.hero .eyebrow {font-size: 12px; letter-spacing: .14em; text-transform: uppercase; color: #FF8FA3; font-weight: 600;}
.hero h1 {font-size: 38px; line-height: 1.1; margin: 6px 0 8px; padding: 0;
  background: linear-gradient(90deg, #FFFFFF 0%, #FFC2CD 55%, #B9A8FF 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent;}
.hero p {color: #B6B7C6; font-size: 15.5px; margin: 0; max-width: 760px;}
.chips {margin-top: 14px; display: flex; gap: 8px; flex-wrap: wrap;}
.chip {font-size: 12.5px; padding: 5px 11px; border-radius: 999px; background: #1C1E29; border: 1px solid #2B2E3D; color: #D9DAE6;}
.chip b {color: #FF8FA3; font-weight: 600;}
.steps {display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 6px 0 18px;}
.step {background: #14161E; border: 1px solid #23263A; border-radius: 14px; padding: 16px;}
.step .n {font-size: 11px; color: #8D8FA3; letter-spacing: .12em; text-transform: uppercase;}
.step .t {font-weight: 650; margin: 4px 0 4px; font-size: 15px;}
.step .d {color: #A3A5B6; font-size: 13px; line-height: 1.45;}
.step .who {display: inline-block; margin-top: 8px; font-size: 11px; padding: 2px 8px; border-radius: 999px;}
.who-code {background: rgba(80,200,160,.13); color: #6EE0B8;}
.who-llm {background: rgba(124,92,255,.16); color: #B9A8FF;}
.kpis {display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 4px 0 12px;}
.kpi {background: #14161E; border: 1px solid #23263A; border-radius: 14px; padding: 14px 16px;}
.kpi .v {font-size: 26px; font-weight: 700; color: #FFFFFF;}
.kpi .l {font-size: 12px; color: #8D8FA3; text-transform: uppercase; letter-spacing: .08em;}
.confbar {display: flex; height: 8px; border-radius: 999px; overflow: hidden; background: #1C1E29; margin: 6px 0 4px;}
.confbar .h {background: #2ECC8F;} .confbar .m {background: #F5B83D;} .confbar .lo {background: #FF5C70;}
.legend {font-size: 12.5px; color: #A3A5B6; margin-bottom: 14px;}
.dot {display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin: 0 5px 0 12px;}
.card {background: #14161E; border: 1px solid #23263A; border-radius: 16px; padding: 18px 20px 14px; margin: 0 0 6px;}
.card.top {border-color: rgba(255,77,109,.55); box-shadow: 0 0 0 1px rgba(255,77,109,.15), 0 10px 30px rgba(255,77,109,.08);}
.head {display: flex; align-items: center; gap: 10px; flex-wrap: wrap;}
.rank {font-size: 22px; font-weight: 800; color: #FFFFFF; min-width: 44px;}
.card.top .rank {color: #FF4D6D;}
.pill {font-size: 12px; padding: 3px 10px; border-radius: 999px; background: #1E2030; border: 1px solid #2B2E3D; color: #D9DAE6;}
.pill.cold {background: rgba(124,92,255,.16); border-color: rgba(124,92,255,.4); color: #CFC4FF;}
.c-high {background: rgba(46,204,143,.14); border-color: rgba(46,204,143,.4); color: #7FE8BE;}
.c-med {background: rgba(245,184,61,.13); border-color: rgba(245,184,61,.4); color: #F7CE74;}
.c-low {background: rgba(255,92,112,.14); border-color: rgba(255,92,112,.4); color: #FF9AA7;}
.score {margin-left: auto; text-align: right;}
.score .v {font-size: 20px; font-weight: 700; color: #FFFFFF;}
.score .l {font-size: 11px; color: #8D8FA3; text-transform: uppercase; letter-spacing: .08em;}
.beats {display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 14px 0 10px;}
.beat {border-radius: 12px; padding: 12px 14px; background: #10121A; border: 1px solid #22253A;}
.beat .k {font-size: 11px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; margin-bottom: 5px;}
.beat.hook .k {color: #FF8FA3;} .beat.cliff .k {color: #B9A8FF;}
.beat.hook {border-left: 3px solid #FF4D6D;} .beat.cliff {border-left: 3px solid #7C5CFF;}
.beat .q {font-size: 14.5px; color: #F1F1F6; line-height: 1.45;}
.why {color: #B6B7C6; font-size: 14px; margin: 2px 0 10px;}
.why b {color: #E9E9F0;}
.tl {margin: 6px 0 4px;}
.tl .row {display: flex; align-items: center; gap: 10px; margin: 5px 0;}
.tl .lab {font-size: 12px; color: #8D8FA3; width: 46px;}
.tl .track {position: relative; flex: 1; height: 10px; background: #1C1E29; border-radius: 999px;}
.tl .seg {position: absolute; top: 0; height: 10px; border-radius: 999px; background: linear-gradient(90deg, #FF4D6D, #7C5CFF);}
.tl .tc {font-size: 12px; color: #A3A5B6; width: 130px; text-align: right; font-variant-numeric: tabular-nums;}
.bars {display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 10px;}
.bar .l {display: flex; justify-content: space-between; font-size: 12px; color: #A3A5B6; margin-bottom: 4px;}
.bar .t {height: 6px; background: #1C1E29; border-radius: 999px; overflow: hidden;}
.bar .f {height: 6px; border-radius: 999px; background: linear-gradient(90deg, #FF4D6D, #FF8FA3);}
.issue {margin-top: 10px; font-size: 13px; color: #F7CE74; background: rgba(245,184,61,.08);
  border: 1px solid rgba(245,184,61,.25); border-radius: 10px; padding: 8px 12px;}
.side-h {font-size: 11px; letter-spacing: .14em; text-transform: uppercase; color: #8D8FA3; margin: 14px 0 2px; font-weight: 600;}
.empty {text-align: center; padding: 26px; border: 1px dashed #2B2E3D; border-radius: 16px; color: #A3A5B6; margin-top: 8px;}
.empty b {color: #FF8FA3;}
@media (max-width: 800px) {
  .steps, .kpis {grid-template-columns: 1fr 1fr;} .beats, .bars {grid-template-columns: 1fr;}
  .hero h1 {font-size: 28px;} .tl .tc {width: 92px;}
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

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


def h(text) -> str:
    return html.escape(str(text or ""))


def show(markup: str):
    st.markdown(markup, unsafe_allow_html=True)


# ---------------------------------------------------------------- header
show('<div class="hero"><div class="eyebrow">Promo Finder · microdrama</div>'
     '<h1>Find the scroll-stopping promos in a whole season</h1>'
     '<p>Reads timestamped screenplays and returns ranked 20 to 60 second clips, each with exact cut '
     'points, ready for an editor to post.</p>'
     '<div class="chips"><span class="chip"><b>Hook</b> in the first 3 s</span>'
     '<span class="chip"><b>Cliffhanger</b> at the cut</span>'
     '<span class="chip"><b>Stands alone</b> for a new viewer</span>'
     '<span class="chip"><b>Legal cuts</b> only, never mid-line</span></div></div>')

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    show('<div class="side-h">1 · Screenplays</div>')
    source = st.radio("Screenplays", ["Sample show (4 invented episodes)", "Upload my own"],
                      label_visibility="collapsed")
    files = []
    if source == "Upload my own":
        files = st.file_uploader("One .txt per episode, or a .zip of them",
                                 type=["txt", "zip"], accept_multiple_files=True)
    st.caption("Processed in memory. Nothing is stored.")

    show('<div class="side-h">2 · Model</div>')
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
    else:
        st.caption("Rules only: free, instant, no key.")

    show('<div class="side-h">3 · Settings</div>')
    top_n = st.slider("Promos to return", 5, 30, cfg["top_n"])
    per_ep = st.slider("Clips per episode sent to the model", 1.0, 4.0, float(cfg["shortlist_per_episode"]), 0.2)
    cold = st.checkbox("Allow cold-open (two-segment) promos", value=cfg["cold_open"]["enabled"])
    ready = source != "Upload my own" or bool(files)
    go = st.button("🎬  Find promos", type="primary", width="stretch",
                   disabled=not ready or (provider != "none" and not api_key))

# ---------------------------------------------------------------- run
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
        with st.status(f"Reading {len(items)} screenplay file(s)…", expanded=True) as status:
            def log(msg):
                status.write(msg)
            try:
                res = run(cfg, items, None, log=log)
                res["meta"]["parse_warnings"] = notes + res["meta"].get("parse_warnings", [])
                res["durations"] = {e.number: e.duration for e in load_show(items)}
                st.session_state["res"] = res
                status.update(label=f"Done: {len(res['promos'])} promos in {res['meta']['runtime_s']} s",
                              state="complete", expanded=False)
            except Exception as e:  # noqa: BLE001  show the reason instead of a stack trace
                status.update(label="The run stopped", state="error", expanded=True)
                st.error(f"The run stopped: {e}")


# ---------------------------------------------------------------- results
def timeline(p, durations) -> str:
    rows = []
    for s in p["segments"]:
        dur = max(durations.get(s["episode"], 0) or 0, s["end"], 1)
        left, width = 100 * s["start"] / dur, max(100 * (s["end"] - s["start"]) / dur, 1.5)
        rows.append(f'<div class="row"><span class="lab">Ep {s["episode"]}</span><div class="track">'
                    f'<div class="seg" style="left:{left:.1f}%;width:{width:.1f}%"></div></div>'
                    f'<span class="tc">{s["start_tc"]} → {s["end_tc"]}</span></div>')
    return '<div class="tl">' + "".join(rows) + "</div>"


def bars(p) -> str:
    sc = p["scores"]
    out = []
    for label, key, llm_key in (("Hook", "hook", "llm_hook_score"), ("Cliffhanger", "cliff", "llm_cliffhanger_score"),
                                ("Stands alone", "standalone", "llm_standalone_score")):
        v = sc[llm_key] / 10 if llm_key in sc else sc[key]
        shown = f"{sc[llm_key]:g}/10" if llm_key in sc else f"{v:.2f}"
        out.append(f'<div class="bar"><div class="l"><span>{label}</span><span>{shown}</span></div>'
                   f'<div class="t"><div class="f" style="width:{max(0, min(1, v)) * 100:.0f}%"></div></div></div>')
    return '<div class="bars">' + "".join(out) + "</div>"


def card(p, durations) -> str:
    label, cls = CONF[p["qa"]["confidence"]]
    kind = '<span class="pill cold">Cold open</span>' if p["type"] == "cold_open" else '<span class="pill">Single stretch</span>'
    eps = ", ".join(str(e) for e in p["episodes"])
    issues = (f'<div class="issue">Check before posting: '
              f'{h("; ".join(ISSUE_TEXT.get(i, i) for i in p["qa"]["issues"]))}</div>' if p["qa"]["issues"] else "")
    hook = h(p["hook"]) or '<span style="color:#8D8FA3">Opens on action, with no spoken line</span>'
    return (f'<div class="card{" top" if p["post_rank"] <= 3 else ""}"><div class="head">'
            f'<span class="rank">#{p["post_rank"]}</span>'
            f'<span class="pill">Episode {eps}</span><span class="pill">{p["duration_s"]:g} s</span>{kind}'
            f'<span class="pill {cls}">{label}</span>'
            f'<div class="score"><div class="v">{p["scores"]["final"]:.2f}</div><div class="l">score</div></div></div>'
            f'<div class="beats"><div class="beat hook"><div class="k">Hook · first 3 s</div><div class="q">{hook}</div></div>'
            f'<div class="beat cliff"><div class="k">Cliffhanger · the cut</div><div class="q">{h(p["cliffhanger"])}</div></div></div>'
            f'<div class="why"><b>Why it works.</b> {h(p["why_it_works"])}</div>'
            f'{timeline(p, durations)}{bars(p)}{issues}</div>')


res = st.session_state.get("res")
if res:
    m, promos, durations = res["meta"], res["promos"], res.get("durations", {})
    conf = {k: sum(p["qa"]["confidence"] == k for p in promos) for k in ("high", "medium", "low")}
    n = max(1, len(promos))
    show('<div class="kpis">'
         f'<div class="kpi"><div class="v">{len(m["episodes"])}</div><div class="l">Episodes read</div></div>'
         f'<div class="kpi"><div class="v">{m["candidates_total"]:,}</div><div class="l">Legal cuts scored</div></div>'
         f'<div class="kpi"><div class="v">{len(promos)}</div><div class="l">Promos ranked</div></div>'
         f'<div class="kpi"><div class="v">{m["runtime_s"]} s</div><div class="l">Runtime · {h(m["model"])}</div></div></div>'
         f'<div class="confbar"><div class="h" style="width:{100 * conf["high"] / n:.1f}%"></div>'
         f'<div class="m" style="width:{100 * conf["medium"] / n:.1f}%"></div>'
         f'<div class="lo" style="width:{100 * conf["low"] / n:.1f}%"></div></div>'
         f'<div class="legend"><span class="dot" style="background:#2ECC8F;margin-left:0"></span>{conf["high"]} high'
         f'<span class="dot" style="background:#F5B83D"></span>{conf["medium"]} check before posting'
         f'<span class="dot" style="background:#FF5C70"></span>{conf["low"]} needs an editor'
         f'<span style="margin-left:14px">· {m["llm_calls"]} model calls</span></div>')
    if m.get("parse_warnings"):
        with st.expander(f"⚠️ {len(m['parse_warnings'])} input warning(s), worked around"):
            for w in m["parse_warnings"]:
                st.write("- " + w)

    t_cards, t_table, t_cov, t_export, t_help = st.tabs(
        ["🎬 Ranked promos", "📋 Table", "📊 Coverage", "⬇️ Export", "ℹ️ How to read"])

    with t_cards:
        st.caption("Posting order: strongest first, spread across episodes, early episodes slightly favoured.")
        for p in promos:
            show(card(p, durations))
            with st.expander(f"Transcript and checks for #{p['post_rank']}"):
                checks = p["qa"]["checks"]
                st.markdown(" · ".join(f"{'✅' if ok else '⚠️'} {CHECK_TEXT.get(k, k)}" for k, ok in checks.items()))
                st.code(p["transcript"], language=None)

    with t_table:
        rows = [{"#": p["post_rank"],
                 "segments": " + ".join(f"Ep{s['episode']} {s['start_tc']}-{s['end_tc']}" for s in p["segments"]),
                 "sec": p["duration_s"], "type": p["type"], "hook": p["hook"], "cliffhanger": p["cliffhanger"],
                 "score": p["scores"]["final"], "confidence": p["qa"]["confidence"],
                 "check": "; ".join(ISSUE_TEXT.get(i, i) for i in p["qa"]["issues"])} for p in promos]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=min(560, 38 + 35 * len(rows)),
                     column_config={"score": st.column_config.ProgressColumn("score", min_value=0, max_value=1, format="%.2f"),
                                    "sec": st.column_config.NumberColumn("sec", format="%.1f s"),
                                    "hook": st.column_config.TextColumn("hook", width="large"),
                                    "cliffhanger": st.column_config.TextColumn("cliffhanger", width="large")})

    with t_cov:
        st.caption("How many picks come from each episode. A good list spreads across the season.")
        per = pd.Series(0, index=m["episodes"], dtype=int)
        for p in promos:
            for e in p["episodes"]:
                per[e] += 1
        st.bar_chart(pd.DataFrame({"promos": per.values}, index=[f"Ep {e:02d}" for e in per.index]),
                     color="#FF4D6D", height=260)

    with t_export:
        st.write("The CSV is the editor's sheet: one row per promo with exact cut points. "
                 "The JSON holds everything, including scores and transcripts.")
        c1, c2 = st.columns(2)
        c1.download_button("Download promos.csv", promos_csv(promos), "promos.csv", "text/csv",
                           type="primary", width="stretch")
        c2.download_button("Download promos.json", json.dumps({k: v for k, v in res.items() if k != "durations"},
                                                              indent=2, ensure_ascii=False),
                           "promos.json", "application/json", width="stretch")

    with t_help:
        st.markdown(
            "- **Order** is the posting order: strongest clips first, spread across episodes, early episodes "
            "slightly favoured so a new viewer can start the show.\n"
            "- **Single stretch** is one continuous cut. **Cold open** flashes 2 to 6 seconds of the payoff, then "
            "plays the build-up that stops just before it.\n"
            "- **Hook** is what the viewer sees in the first 3 seconds; **cliffhanger** is the last beat before the cut.\n"
            "- **Timeline** shows where the clip sits in its episode.\n"
            "- **Confidence**: green means every check passed; amber and red say what an editor should check.\n"
            "- In rules-only mode scores come from code alone; a model run re-scores the shortlist out of 10.")
else:
    show('<div class="steps">'
         '<div class="step"><div class="n">Step 1</div><div class="t">Parse</div><div class="d">Every scene, line and action becomes a timestamped event. Bad lines are reported, not fatal.</div><span class="who who-code">code</span></div>'
         '<div class="step"><div class="n">Step 2</div><div class="t">Cut</div><div class="d">Every legal 20 to 60 s cut on a shot boundary, plus cold opens. About 13,000 for 50 episodes.</div><span class="who who-code">code</span></div>'
         '<div class="step"><div class="n">Step 3</div><div class="t">Judge</div><div class="d">Rules score hook, cliffhanger and standalone sense. An optional model re-judges the shortlist like a stranger would.</div><span class="who who-llm">rules + LLM</span></div>'
         '<div class="step"><div class="n">Step 4</div><div class="t">Rank and check</div><div class="d">A posting order across episodes, with a confidence flag and the reason on every pick.</div><span class="who who-code">code</span></div>'
         '</div>'
         '<div class="empty">Choose the <b>sample show</b> or upload screenplays in the sidebar, then press '
         '<b>Find promos</b>.<br>Provider <b>none</b> is free and needs no key.</div>')

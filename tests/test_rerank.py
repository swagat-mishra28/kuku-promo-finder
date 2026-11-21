"""Listwise rerank stage: parsing, shuffle seeds, bad JSON, missing clips, and a full run against a fake
OpenAI-compatible server through the real LLM layer. Invented text only."""
import copy
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import promo_finder.llm as L
from promo_finder.candidates import Candidate, Segment
from promo_finder.llm import LLM
from promo_finder.parser import load_show
from promo_finder.pipeline import rerank_stage
from promo_finder.rerank import RERANK_VERSION, batches_for_pass, parse_ranking


def test_parse_full_ranking():
    s, probs = parse_ranking({"ranking": [{"id": "C3", "reason": "x"}, {"id": "C1"}, {"id": "C2"}]}, ["C1", "C2", "C3"])
    assert s == {"C3": 1.0, "C1": 0.5, "C2": 0.0} and probs == []


def test_parse_missing_unknown_and_repeated_ids():
    s, probs = parse_ranking({"ranking": [{"id": "C2"}, {"id": "C9"}, {"id": "C2"}, {"id": "C1"}]},
                             ["C1", "C2", "C3", "C4"])
    assert s["C2"] == 1.0 and s["C1"] == pytest.approx(2 / 3)
    assert s["C3"] == 0.5 and s["C4"] == 0.5                     # missing -> neutral
    assert any("C9" in p for p in probs) and any("C3 missing" in p for p in probs)


def test_parse_bad_shape_is_neutral():
    s, probs = parse_ranking({"order": ["C1"]}, ["C1", "C2"])
    assert s == {"C1": 0.5, "C2": 0.5} and "no 'ranking' list" in probs[0]
    s, _ = parse_ranking({"ranking": ["C2", "C1"]}, ["C1", "C2"])  # plain id strings are accepted
    assert s == {"C2": 1.0, "C1": 0.0}


def test_shuffle_is_seeded_and_covers_every_clip_once():
    a, b, c = batches_for_pass(30, 10, 17), batches_for_pass(30, 10, 17), batches_for_pass(30, 10, 29)
    assert a == b and a != c
    for batches in (a, c):
        assert [len(x) for x in batches] == [10, 10, 10]
        assert sorted(i for x in batches for i in x) == list(range(30))


# ---------------- fake OpenAI-compatible server ----------------
@pytest.fixture
def fake_api():
    state = {"calls": [], "mode": "reverse"}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            user = body["messages"][1]["content"]
            state["calls"].append(body)
            ids = re.findall(r"^CLIP (C\d+) ", user, re.M)
            mode = state["mode"]
            if mode == "bad_json":
                content = "Sorry, I cannot rank these."
            elif mode == "missing_one":
                content = json.dumps({"ranking": [{"id": i, "reason": "r"} for i in ids[:-1]]})
            elif mode == "rate_limit":
                self.send_response(429); self.end_headers(); self.wfile.write(b'{"error":"rate_limit"}')
                return
            else:   # reverse: highest id number first, deterministic
                order = sorted(ids, key=lambda i: -int(i[1:]))
                content = json.dumps({"ranking": [{"id": i, "reason": "stronger hook"} for i in order]})
            data = json.dumps({"choices": [{"message": {"content": content}}],
                               "usage": {"prompt_tokens": 3500, "completion_tokens": 400}}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/v1", state
    srv.shutdown()


@pytest.fixture
def setup(show_dir, cfg, tmp_path, monkeypatch, fake_api):
    base_url, state = fake_api
    monkeypatch.setenv("PROMO_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("PROMO_LLM_MODEL", "fake-judge")
    monkeypatch.setenv("PROMO_LLM_BASE_URL", base_url)
    monkeypatch.setattr(L.time, "sleep", lambda s: None)          # no retry waits in tests
    eps = {e.number: e for e in load_show(show_dir)}
    cfg = copy.deepcopy(cfg)
    cfg["rerank"].update(enabled=True, top_k=12, batch_size=4, seeds=[17, 29])
    cfg["llm"].update(cache_dir=str(tmp_path / "cache"), min_seconds_between_calls=0)
    shortlist = []
    for n in (1, 2, 3):
        for k in range(5):
            c = Candidate("single", [Segment(n, 4.0 * k, 4.0 * k + 24.0)])
            c.final = round(0.9 - 0.01 * (5 * (n - 1) + k), 4)
            c.llm = {}
            shortlist.append(c)
    return cfg, eps, shortlist, state


def test_rerank_with_fake_server_reorders_inside_the_band(setup):
    cfg, eps, shortlist, state = setup
    before = sorted((c.final for c in shortlist), reverse=True)
    original = [c.final for c in shortlist]
    info = rerank_stage(shortlist, eps, cfg, LLM(cfg["llm"]), log=lambda *a: None)
    assert info["reranked"] >= 2 and info["calls"] == len(state["calls"])
    assert all(RERANK_VERSION in call["messages"][0]["content"] for call in state["calls"])
    assert "EPISODE SUMMARY" not in state["calls"][0]["messages"][1]["content"]   # cold viewer: no summary
    scored = [c for c in shortlist if "rerank_score" in c.llm]
    assert len(scored) == info["reranked"]
    band = sorted((c.final for c in scored), reverse=True)
    assert band == before[: len(band)] or set(band) <= set(before)                 # same band of finals
    # Second run: every batch prompt is cached, no new calls.
    n = len(state["calls"])
    for c, f in zip(shortlist, original):     # same clips and scores as the first run
        c.llm.pop("rerank_score", None)
        c.final = f
    rerank_stage(shortlist, eps, cfg, LLM(cfg["llm"]), log=lambda *a: None)
    assert len(state["calls"]) == n


def test_bad_json_reply_scores_batch_neutral_without_crashing(setup):
    cfg, eps, shortlist, state = setup
    state["mode"] = "bad_json"
    notes = []
    info = rerank_stage(shortlist, eps, cfg, LLM(cfg["llm"]), log=notes.append)
    assert info["reranked"] >= 2
    assert all(c.llm.get("rerank_score") == 0.5 for c in shortlist if "rerank_score" in c.llm)
    assert any("bad reply" in n for n in notes)


def test_missing_clip_in_reply_is_neutral(setup):
    cfg, eps, shortlist, state = setup
    state["mode"] = "missing_one"
    notes = []
    rerank_stage(shortlist, eps, cfg, LLM(cfg["llm"]), log=notes.append)
    assert any("missing from the reply" in n for n in notes)


def test_rate_limit_stops_and_keeps_blend_order(setup):
    cfg, eps, shortlist, state = setup
    state["mode"] = "rate_limit"
    before = [c.final for c in shortlist]
    info = rerank_stage(shortlist, eps, cfg, LLM(cfg["llm"]), log=lambda *a: None)
    assert info["reranked"] == 0 and "stopped_on_error" in info
    assert [c.final for c in shortlist] == before and len(state["calls"]) == 1


def test_off_by_default(cfg, show_dir):
    eps = {e.number: e for e in load_show(show_dir)}
    c = Candidate("single", [Segment(1, 0, 24)])
    c.final, c.llm = 0.5, {}
    assert cfg["rerank"]["enabled"] is False
    assert rerank_stage([c], eps, cfg, None) == {}

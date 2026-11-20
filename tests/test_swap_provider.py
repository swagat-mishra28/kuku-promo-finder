"""The model is swappable: the full pipeline runs against any OpenAI-compatible endpoint.

A tiny local HTTP server stands in for Kuku's API and returns canned judge JSON.
The real llm.py code path is used (HTTP, JSON mode, token counting, disk cache).
"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from promo_finder.pipeline import run

CANNED = {"hook_quote": "Seize her!", "hook_score": 8, "cliffhanger_quote": "It is a warning.",
          "cliffhanger_score": 7, "standalone_score": 6, "confusing_for_new_viewer": "",
          "why_it_works": "Clear threat and an open ending.", "biggest_weakness": "short", "overall": 7}


@pytest.fixture
def fake_api():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
            out = {"choices": [{"message": {"content": json.dumps(CANNED)}}],
                   "usage": {"prompt_tokens": 900, "completion_tokens": 120}}
            data = json.dumps(out).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/v1", calls
    srv.shutdown()


def test_full_pipeline_with_a_swapped_provider(show_dir, cfg, fake_api, tmp_path, monkeypatch):
    base_url, calls = fake_api
    # The three config lines Kuku would change (README: "Plug in your own model"):
    monkeypatch.setenv("PROMO_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("PROMO_LLM_MODEL", "kuku-judge-1")
    monkeypatch.setenv("PROMO_LLM_BASE_URL", base_url)
    cfg["shortlist_size"], cfg["shortlist_per_episode"] = 10, 0      # judge 10 clips
    cfg["llm"].update(cache_dir=str(tmp_path / "cache"), min_seconds_between_calls=0, reasoning_effort="low")

    res = run(cfg, str(show_dir), str(tmp_path / "out"), log=lambda *a: None)

    meta = res["meta"]
    assert meta["model"] == "openai_compatible:kuku-judge-1"
    # Up to 10 clips go to the judge; three short test episodes may have fewer distinct moments.
    assert 5 <= meta["shortlist"] <= 10
    assert meta["shortlist"] == len(calls) == meta["llm_calls"]
    assert meta["tokens_in"] == 900 * len(calls) and meta["tokens_out"] == 120 * len(calls)
    assert calls[0]["path"] == "/v1/chat/completions"
    assert calls[0]["body"]["model"] == "kuku-judge-1"
    assert calls[0]["body"]["reasoning_effort"] == "low"
    assert calls[0]["auth"] == "Bearer test-key-not-real"
    assert all(p["scores"].get("llm_overall") == 7 for p in res["promos"])
    for f in ("promos.json", "promos.csv", "promos.md", "run_meta.json", "shortlist_all_scored.json"):
        assert (tmp_path / "out" / f).exists()

    # Second run: every answer comes from the disk cache, zero new calls.
    n = len(calls)
    res2 = run(cfg, str(show_dir), str(tmp_path / "out2"), log=lambda *a: None)
    assert len(calls) == n and res2["meta"]["llm_cache_hits"] == n and res2["meta"]["llm_calls"] == 0


def test_cli_provider_none_beats_env(show_dir, tmp_path, monkeypatch):
    """Regression for F07: .env said groq, --provider none must still make zero calls."""
    import promo_finder.llm as L

    def boom(*a, **k):
        raise AssertionError("an LLM call was attempted")

    monkeypatch.setattr(L.LLM, "_call", boom)
    monkeypatch.setenv("PROMO_LLM_PROVIDER", "groq")
    import run as cli
    monkeypatch.setattr(sys, "argv", ["run.py", "--provider", "none", "--episodes", str(show_dir),
                                      "--out", str(tmp_path / "o")])
    cli.main()
    meta = json.loads((tmp_path / "o" / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["model"] == "rules-only" and meta["llm_calls"] == 0

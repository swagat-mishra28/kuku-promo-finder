"""Web app input handling: in-memory uploads, the sample show, and key isolation."""
import io
import zipfile

import pytest
import yaml
from conftest import ROOT, screenplay

from promo_finder.llm import LLM
from promo_finder.parser import load_show
from promo_finder.pipeline import promos_csv, run
from promo_finder.uploads import read_uploads


class Upload:
    def __init__(self, name, data):
        self.name, self._data = name, data

    def getvalue(self):
        return self._data


def zipped(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()


def test_many_txt_and_a_zip(tmp_path):
    ups = [Upload(f"ep{n}.txt", screenplay(n).encode()) for n in range(1, 41)]
    ups.append(Upload("more.zip", zipped({"season/episode_041.txt": screenplay(41),
                                           "__MACOSX/._episode_041.txt": "junk",
                                           "notes.pdf": "not a screenplay"})))
    items, notes = read_uploads(ups)
    assert len(items) == 41 and notes == []
    eps = load_show(items)
    assert [e.number for e in eps] == list(range(1, 42))


def test_bad_zip_duplicates_and_limits():
    ups = [Upload("broken.zip", b"not a zip"), Upload("a.txt", b"x"), Upload("a.txt", b"y"),
           Upload("big.txt", b"x" * 2048)]
    items, notes = read_uploads(ups, max_mb=0.001)
    assert [n for n, _ in items] == ["a.txt"]
    assert any("not a readable zip" in n for n in notes)
    assert any("already uploaded" in n for n in notes)
    assert any("larger than" in n for n in notes)


def test_in_memory_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    cfg["llm"].update(provider="none", from_env=False, cache=False)
    items = [(f"episode_{n:03d}.txt", screenplay(n).encode()) for n in (1, 2, 3)]
    res = run(cfg, items, None, log=lambda m: None)
    assert res["promos"] and list(tmp_path.iterdir()) == []
    assert promos_csv(res["promos"]).startswith("post_rank,")


def test_sample_show_parses_cleanly():
    eps = load_show(ROOT / "data" / "sample")
    assert [e.number for e in eps] == [1, 2, 3, 4]
    assert not [w for e in eps for w in e.warnings]
    assert all(80 <= e.duration <= 100 for e in eps)


def test_app_mode_ignores_environment(monkeypatch):
    """A key or provider left in the server's environment must not leak into a visitor's run."""
    monkeypatch.setenv("PROMO_LLM_PROVIDER", "groq")
    monkeypatch.setenv("PROMO_LLM_API_KEY", "someone-elses-key")
    llm = LLM({"provider": "none", "from_env": False, "cache": False})
    assert not llm.enabled and llm.api_key == ""
    llm = LLM({"provider": "groq", "api_key": "visitor-key", "from_env": False, "cache": False})
    assert llm.api_key == "visitor-key"


def test_app_sample_run_with_apptest():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert at.selectbox[0].value == "none"
    at.button[0].click().run()
    assert not at.exception
    assert len(at.dataframe) == 1 and len(at.dataframe[0].value) > 0

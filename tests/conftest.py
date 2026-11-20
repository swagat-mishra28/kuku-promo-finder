"""Shared fixtures. Every screenplay here is invented test text, never Kuku's content."""
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

LINES = [
    ("MARA (Furious, Shouting)", "You lied to me in front of everyone!"),
    ("ACTION", "Mara shoves the ledger off the table."),
    ("TOBIAS (Cold, Mocking)", "And who would believe a thief's daughter?"),
    ("MARA (Desperate)", "My father never stole anything."),
    ("SFX", "A door slams somewhere above."),
    ("GUARD (Harsh)", "Seize her!"),
    ("MARA (Screaming)", "Let me go!"),
    ("TOBIAS (Gloating)", "Tomorrow you hang beside him."),
    ("MARA (Defiant)", "Then I will drag the truth up with me."),
    ("ACTION", "The guard drags Mara toward the cellar stairs."),
    ("TOBIAS (Quiet, Menacing)", "Is that a promise?"),
    ("MARA (Steely)", "It is a warning."),
]


def tc(sec: float) -> str:
    m, s = divmod(sec, 60)
    return f"{int(m):02d}:{s:05.2f}"


def screenplay(number: int | None, seconds: float = 96.0, header: bool = True) -> str:
    """A small screenplay in the Kuku format: a camera shot every 4 s, one beat inside each shot."""
    out = []
    if header and number is not None:
        out.append(f"EPISODE NUMBER: Episode {number}")
    out += ["EPISODE LOGLINE: Test episode.", "CONTINUITY NOTES: None.", "", "--- SCRIPT START ---", "",
            "SCENE 01", "Scene heading: INT. HALL - NIGHT", "", "Actions and dialogue:", ""]
    t, i = 0.0, 0
    while t + 4.0 <= seconds + 1e-6:
        out += ["**CAMERA:**", f"Start: ({tc(t)}) | End: ({tc(t + 4.0)})",
                f"Shot {i} of the hall in episode {number}.", ""]   # unique text per episode
        label, text = LINES[i % len(LINES)]
        out += [f"**{label}:**", f"Start: ({tc(t + 0.5)}) | End: ({tc(t + 3.5)})", text, ""]
        t += 4.0
        i += 1
    return "\n".join(out) + "\n"


@pytest.fixture
def show_dir(tmp_path):
    """Three clean 96-second episodes."""
    d = tmp_path / "show"
    d.mkdir()
    for n in (1, 2, 3):
        (d / f"episode_{n:03d}.txt").write_text(screenplay(n), encoding="utf-8")
    return d


@pytest.fixture
def cfg():
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    """Tests never reach a real provider, whatever .env says."""
    monkeypatch.setenv("PROMO_LLM_PROVIDER", "none")
    monkeypatch.delenv("PROMO_LLM_MODEL", raising=False)
    monkeypatch.delenv("PROMO_LLM_BASE_URL", raising=False)
    monkeypatch.setenv("PROMO_LLM_API_KEY", "test-key-not-real")
    import promo_finder.llm as L
    monkeypatch.setattr(L, "load_dotenv", lambda *a, **k: None)

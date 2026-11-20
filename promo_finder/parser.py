"""Parse Kuku-style microdrama screenplays into structured, timestamped events.

Deterministic code, no AI. Every downstream step (candidates, scoring, LLM prompts)
works on these events, so the parser is strict about timestamps and lenient about
formatting (headings in mixed case, O.S./V.O. tags, "(Off-screen)", etc.).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

TS = r"\((\d+):(\d+(?:\.\d+)?)\)"
TIME_RE = re.compile(rf"Start:\s*{TS}\s*\|\s*End:\s*{TS}", re.I)
TAG_RE = re.compile(r"^\*\*(.+?):\*\*\s*$")
SCENE_RE = re.compile(r"^SCENE\s+(\d+)", re.I)
HEADING_RE = re.compile(r"^Scene heading:\s*(.+)$", re.I)

NON_DIALOGUE = {"CAMERA", "ACTION", "SOUND FX", "SFX", "MUSIC"}


def _secs(m: str, s: str) -> float:
    return int(m) * 60 + float(s)


@dataclass
class Event:
    episode: int
    idx: int
    kind: str            # camera | action | sfx | dialogue
    start: float
    end: float
    text: str
    speaker: str = ""    # raw speaker label for dialogue
    tone: str = ""       # e.g. "Cold, Callous"
    offscreen: bool = False  # O.S. / V.O. / Off-screen
    scene: int = 0
    heading: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class Episode:
    number: int
    logline: str
    continuity: str
    events: list[Event] = field(default_factory=list)
    path: str = ""
    warnings: list[str] = field(default_factory=list)   # parse problems found and worked around

    @property
    def duration(self) -> float:
        return max((e.end for e in self.events), default=0.0)

    @property
    def shots(self) -> list[Event]:
        return [e for e in self.events if e.kind == "camera"]

    @property
    def lines(self) -> list[Event]:
        return [e for e in self.events if e.kind == "dialogue"]


def _split_label(label: str):
    """'LORD ASHCROFT (O.S. / Continues)' -> name, tone, offscreen."""
    parts = re.findall(r"\(([^)]*)\)", label)
    name = re.sub(r"\(.*", "", label).strip()
    off = False
    tones = []
    for p in parts:
        if re.search(r"\b(O\.S\.|V\.O\.|Off-?screen|Continu)", p, re.I):
            off = off or bool(re.search(r"O\.S\.|V\.O\.|Off-?screen", p, re.I))
        else:
            tones.append(p.strip())
    return name, ", ".join(tones), off


def _number_from_name(stem: str):
    """Episode number from a file name: prefer 'ep'/'episode'/'e' + digits, else the last number."""
    m = re.search(r"(?:episode|ep|e)[\s_\-.]*0*(\d+)", stem, re.I)
    if m:
        return int(m.group(1))
    nums = re.findall(r"\d+", stem)
    return int(nums[-1]) if nums else None


def parse_episode(path: str | Path) -> Episode:
    path = Path(path)
    warnings = []
    # utf-8-sig drops a byte-order mark; errors="replace" keeps a bad byte from killing the run.
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if "�" in text:
        warnings.append(f"{path.name}: some bytes were not valid UTF-8 and were replaced")
    raw = text.splitlines()
    meta = {"EPISODE NUMBER": "", "EPISODE LOGLINE": "", "CONTINUITY NOTES": ""}
    for line in raw[:15]:
        line = line.strip().lstrip("﻿")   # stray byte-order marks survive strip()
        for k in meta:
            if line.upper().startswith(k + ":"):
                meta[k] = line.split(":", 1)[1].strip()
    num_m = re.search(r"(\d+)", meta["EPISODE NUMBER"])
    if num_m:
        number = int(num_m.group(1))
    else:
        number = _number_from_name(path.stem)
        if number is None:
            number = 0   # load_show gives it a free number and says so
            warnings.append(f"{path.name}: no EPISODE NUMBER header and no number in the file name")
        else:
            warnings.append(f"{path.name}: no EPISODE NUMBER header; took episode {number} from the file name")
    ep = Episode(number, meta["EPISODE LOGLINE"], meta["CONTINUITY NOTES"], path=str(path))
    ep.warnings = warnings

    scene, heading = 0, ""
    i, n = 0, len(raw)
    while i < n:
        line = raw[i].strip()
        if (m := SCENE_RE.match(line)):
            scene = int(m.group(1))
        elif (m := HEADING_RE.match(line)):
            heading = m.group(1).strip()
        elif (m := TAG_RE.match(line)):
            label = m.group(1).strip()
            # find timing line then text (skip blanks)
            j = i + 1
            while j < n and not raw[j].strip():
                j += 1
            tm = TIME_RE.search(raw[j]) if j < n else None
            if not tm:
                shown = raw[j].strip()[:60] if j < n else "end of file"
                ep.warnings.append(f"{path.name} line {i + 1}: skipped **{label}** block, "
                                   f"no valid 'Start: (mm:ss) | End: (mm:ss)' line (found: {shown!r})")
            if tm:
                k = j + 1
                while k < n and not raw[k].strip():   # tolerate blank lines before the text
                    k += 1
                text_lines = []
                while k < n and raw[k].strip() and not TAG_RE.match(raw[k].strip()) \
                        and not SCENE_RE.match(raw[k].strip()) and not raw[k].startswith("---"):
                    text_lines.append(raw[k].strip())
                    k += 1
                text = " ".join(text_lines).strip().strip('"').strip("“”")
                start = _secs(tm.group(1), tm.group(2))
                end = _secs(tm.group(3), tm.group(4))
                if end < start:
                    ep.warnings.append(f"{path.name} line {j + 1}: end before start, swapped")
                    start, end = end, start
                if not text_lines:
                    ep.warnings.append(f"{path.name} line {j + 1}: **{label}** block has no text")
                name, tone, off = _split_label(label)
                upper = name.upper()
                if upper in NON_DIALOGUE:
                    kind = {"CAMERA": "camera", "ACTION": "action"}.get(upper, "sfx")
                    ev = Event(ep.number, len(ep.events), kind, start, end, text,
                               tone=tone, scene=scene, heading=heading)
                else:
                    ev = Event(ep.number, len(ep.events), "dialogue", start, end, text,
                               speaker=name, tone=tone, offscreen=off, scene=scene, heading=heading)
                ep.events.append(ev)
                i = k
                continue
        i += 1
    ep.events.sort(key=lambda e: (e.start, e.end))
    for k, e in enumerate(ep.events):
        e.idx = k
    if not ep.events:
        ep.warnings.append(f"{path.name}: no events found; is this a screenplay in the expected format?")
    return ep


def load_show(folder: str | Path) -> list[Episode]:
    """Parse every .txt in a folder. Never crashes on one bad file; problems go into Episode.warnings."""
    files = sorted(Path(folder).glob("*.txt"))
    eps, seen = [], {}
    for f in files:
        try:
            ep = parse_episode(f)
        except Exception as e:  # noqa: BLE001  one unreadable file should not stop the show
            bad = Episode(0, "", "", path=str(f))
            bad.warnings.append(f"{f.name}: could not be parsed ({type(e).__name__}: {e}); skipped")
            eps.append(bad)
            continue
        if ep.number in seen and ep.number != 0:
            ep.warnings.append(f"{f.name}: episode {ep.number} already loaded from {seen[ep.number]}; skipped")
            ep.events = []
        else:
            seen[ep.number] = f.name
        eps.append(ep)
    # Files without a number get the next free one, after the numbered episodes.
    nxt = max(seen, default=0) + 1
    for ep in eps:
        if ep.number == 0 and ep.events:
            ep.number = nxt
            for e in ep.events:
                e.episode = nxt
            ep.warnings.append(f"{Path(ep.path).name}: assigned episode number {nxt}")
            nxt += 1
    good = sorted([e for e in eps if e.events], key=lambda e: e.number)
    nums = [e.number for e in good]
    missing = sorted(set(range(min(nums), max(nums) + 1)) - set(nums)) if nums else []
    if missing:
        good[0].warnings.append(f"episode numbers missing from the input: {missing}")
    # Episodes with no events are dropped from the show but keep their warnings visible.
    dropped = [w for e in eps if not e.events for w in e.warnings]
    if good and dropped:
        good[0].warnings.extend(dropped)
    if not good and eps:
        raise ValueError("no usable episodes: " + "; ".join(w for e in eps for w in e.warnings))
    return good


if __name__ == "__main__":
    import sys
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    show = load_show(sys.argv[1] if len(sys.argv) > 1 else "data/episodes")
    for ep in show:
        print(f"Ep {ep.number:>3}: {len(ep.events):>3} events, {len(ep.lines):>3} lines, "
              f"{len(ep.shots):>3} shots, {ep.duration:6.1f}s")
    warns = [w for ep in show for w in ep.warnings]
    print(f"\nParse warnings: {len(warns)}")
    for w in warns:
        print(f"  WARNING {w}")

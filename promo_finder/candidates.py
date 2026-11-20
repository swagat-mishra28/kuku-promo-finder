"""Generate promo candidates from parsed episodes (pure code, no AI).

Cut rules an editor would apply:
  * a promo starts at the start of a camera shot and ends at the end of one
  * never cut through a line of dialogue
  * total length 20-60 s (configurable)

Two candidate shapes:
  single     one continuous stretch inside one episode
  cold_open  a 1.5-6 s "flash-forward" hook taken from later in the story
             (same or next episode), followed by a continuous body that ends
             just before that moment. This is the standard ReelShort/DramaBox ad
             shape: show the slap first, then rewind and stop before it lands.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from .parser import Episode, Event


@dataclass
class Segment:
    episode: int
    start: float
    end: float

    @property
    def dur(self) -> float:
        return self.end - self.start

    def to_dict(self):
        return {"episode": self.episode, "start": round(self.start, 2), "end": round(self.end, 2),
                "start_tc": tc(self.start), "end_tc": tc(self.end)}


@dataclass
class Candidate:
    kind: str
    segments: list[Segment]
    events: list[Event] = field(default_factory=list)   # events inside, in play order
    features: dict = field(default_factory=dict)
    score: float = 0.0
    llm: dict = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return sum(s.dur for s in self.segments)

    @property
    def key(self) -> str:
        return "|".join(f"{s.episode}:{s.start:.1f}-{s.end:.1f}" for s in self.segments)


def tc(sec: float) -> str:
    m, s = divmod(sec, 60)
    return f"{int(m):02d}:{s:05.2f}"


def _straddles(ep: Episode, t: float, tol: float = 0.25) -> bool:
    """True if a dialogue line is being spoken across time t."""
    return any(e.start + tol < t < e.end - tol for e in ep.lines)


def cut_points(ep: Episode):
    starts = sorted({round(s.start, 2) for s in ep.shots if not _straddles(ep, s.start)})
    ends = sorted({round(s.end, 2) for s in ep.shots if not _straddles(ep, s.end)})
    if not starts:
        starts = [0.0]
    if not ends:
        ends = [ep.duration]
    return starts, ends


def events_in(ep: Episode, a: float, b: float, tol: float = 0.15) -> list[Event]:
    return [e for e in ep.events if e.start >= a - tol and e.end <= b + tol + 0.6 and e.start < b]


def single_candidates(ep: Episode, min_len=20, max_len=60) -> list[Candidate]:
    starts, ends = cut_points(ep)
    out = []
    for s in starts:
        for e in ends:
            d = e - s
            if min_len <= d <= max_len:
                seg = Segment(ep.number, s, e)
                out.append(Candidate("single", [seg], events_in(ep, s, e)))
    return out


def hook_clips(ep: Episode, min_len=1.5, max_len=6.0) -> list[tuple[Segment, Event]]:
    """Short clips around one dialogue line or action beat, snapped to shots."""
    starts, ends = cut_points(ep)
    clips = []
    for ev in ep.events:
        if ev.kind not in ("dialogue", "action"):
            continue
        s = max([x for x in starts if x <= ev.start + 0.05], default=None)
        e = min([x for x in ends if x >= ev.end - 0.05], default=None)
        if s is None or e is None:
            continue
        if min_len <= e - s <= max_len:
            clips.append((Segment(ep.number, s, e), ev))
    return clips


def cold_open_candidates(eps: dict[int, Episode], base: list[Candidate], hooks_by_ep: dict,
                         min_len=20, max_len=60, top_bodies=60, max_gap=25.0) -> list[Candidate]:
    """Pair a strong hook clip with a body that stops just before that hook happens.

    The hook must be the payoff the body is building to: at most `max_gap` seconds
    of story after the body ends (same episode), or in the opening of the next
    episode when the body ends on this episode's final beat. A random flash from
    elsewhere in the show would confuse a new viewer, so it is not allowed.
    """
    out = []
    bodies = sorted(base, key=lambda c: c.features.get("cliff", 0), reverse=True)[:top_bodies]
    for body in bodies:
        b = body.segments[0]
        for ep_no in (b.episode, b.episode + 1):
            for seg, ev in hooks_by_ep.get(ep_no, []):
                if ep_no == b.episode:
                    gap = seg.start - b.end
                    if gap < 0.5 or gap > max_gap:
                        continue
                else:
                    if b.end < eps[b.episode].duration - 1.0 or seg.start > max_gap:
                        continue
                total = body.duration + seg.dur
                if not (min_len <= total <= max_len):
                    continue
                hep = eps[ep_no]
                c = Candidate("cold_open", [seg, b], events_in(hep, seg.start, seg.end) + body.events)
                c.features["_hook_event"] = ev
                out.append(c)
    return out

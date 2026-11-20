"""Rule-based scoring of promo candidates (no AI, runs offline, free).

Each candidate gets four sub-scores in [0, 1]:
  hook        how hard the first 3 seconds stop a scroll
  cliff       how unresolved the last beat is
  standalone  can a stranger follow it
  heat        conflict / emotion density across the whole clip
The weights live in config.yaml. These rules are a cheap first filter: they cut
~20k possible clips down to a shortlist that the LLM judge (judge.py) re-scores.
"""
from __future__ import annotations

import math
import re

from .candidates import Candidate
from .parser import Episode

HOT_TONES = r"furious|scream|shout|roar|venom|cruel|gloat|mock|desperate|outrag|enrag|livid|horrif|" \
            r"menac|threat|lethal|defiant|accus|heartbro|devastat|sob|panic|terrif|agon|boom|imperious|" \
            r"hysteric|shriek|callous|scorn|sneer|spite|vicious|harsh|brutal|disgust|pleading|begging|" \
            r"betray|shatter|crush|choked|fierce|piercing|savage|taunt|derisive|condescend"
STAKES = r"disown|betray|marry|married|wedding|wife|husband|hang|gallows|arrest|stole|steal|theft|" \
         r"dead to|never|knew|lie|liar|sister|father|mother|duke|kill|disappear|blood|bleed|worthless|" \
         r"beggar|penniless|plain|inheritance|dowry|revoked|thief|search|proof|planted|vow|swear|swore|" \
         r"ashamed|humiliat|choose|chose|nobody|crawl|bare hands|ring|watch|poison|arsenic|witch|execut|" \
         r"condemn|sentence|dungeon|cell|chain|prisoner|traitor|treason|alive|dead|imposter|impostor|" \
         r"arrest|burn|duke|duchess|title|wife|lie|secret"
PHYSICAL = r"slap|strike|struck|punch|grab|seiz|shove|drag|fling|flings|hurl|throw|blood|kneel|drops to|" \
           r"lunge|collapse|handcuff|cuffs|wrench|snatch|tear|smash|crash|chok|lift|stab|gash|slam|point|" \
           r"explo|fireball|flame|fire|blaze|inferno|poker|branding|whip|crop|shackle|chain|kick|tackle|" \
           r"shatter|detonat|gasp|convuls|blade|sword|sabre"
CLIFF_SFX = r"cliffhanger|ominous|tense|freeze|cut to black|cuts to black|drone|boom|gasp|peak|suspend|" \
            r"dread|horror|terror|shock|frozen|reveal|vengeance|lethal|disbelief|knife's edge"
CALM = r"\bthank you\b|\bit is over\b|\bpeaceful|\bsafe\b|\brelief\b|\bsmil(e|es|ing)\b|\blaugh(s|ing)?\b(?! at)|" \
       r"\bwarm(ly|th)?\b|\btender(ly)?\b|\bembrac|\bgentle\b|\bgently\b|\bcontent(ed)?\b|\bcomfort|\bgrateful\b|" \
       r"\bsoft(ly)?\b|\bfades? (out|to)|\bhope\b|\bserenity\b|\bi accept\b|\bi will wait\b|\bsunlight\b|" \
       r"\bhand-in-hand\b|\bnestl"
# Words that describe HOW a line is delivered. In a tone tag they are not a resolved ending.
DELIVERY = r"\bsoft(ly)?\b|\bgentle\b|\bgently\b|\btender(ly)?\b|\bwarm(ly|th)?\b"
# Big late beats that can end a clip even when the last line is quiet (entrances, reveals, impacts).
LATE_BEAT = r"explo|detonat|fireball|bursts? (in|open|through)|storms? (in|into)|emerg|appears|enters|" \
            r"walks (in|through)|reveal|unmask|collaps|crash|shatter|gunshot|scream|slams? (open|shut)|" \
            r"freeze|frozen|holds on|cut to black|cuts to black"
CONTINUATION = re.compile(r"^(\.\.\.|…|and\b|but\b|then\b|so\b|or\b|because\b|[a-z])")


def rx(pattern: str, text: str) -> int:
    return len(re.findall(pattern, text.lower()))


def line_heat(ev) -> float:
    """0..1 intensity of one event."""
    t = ev.text
    tone = ev.tone.lower()
    s = 0.0
    s += 0.35 * min(1, rx(HOT_TONES, tone))
    s += 0.20 * min(1, t.count("!"))
    s += 0.25 * min(1, rx(STAKES, t) / 1.5)
    s += 0.20 * min(1, rx(PHYSICAL, t + " " + tone))
    if ev.kind == "dialogue" and len(t.split()) <= 9:
        s += 0.10   # short lines punch harder on mute-scroll with captions
    if ev.kind == "camera":
        s *= 0.4    # camera notes describe, they don't happen
    return min(1.0, s)


def timeline(c: Candidate, eps: dict[int, Episode]):
    """[(event, play_start, play_end)] in the order the viewer sees them."""
    out, off = [], 0.0
    for seg in c.segments:
        ep = eps[seg.episode]
        for e in ep.events:
            if e.start >= seg.start - 0.15 and e.start < seg.end - 0.1:
                out.append((e, off + e.start - seg.start, off + min(e.end, seg.end) - seg.start))
        off += seg.dur
    return out


def score_candidate(c: Candidate, eps: dict[int, Episode], cfg: dict) -> Candidate:
    tl = timeline(c, eps)
    dur = c.duration
    talk = [x for x in tl if x[0].kind == "dialogue"]
    beats = [x for x in tl if x[0].kind in ("dialogue", "action", "sfx")]

    # ---------- hook: first 3 seconds ----------
    first = [x for x in beats if x[1] <= 3.0]
    hook_ev = max(first, key=lambda x: line_heat(x[0]), default=None)
    hook = line_heat(hook_ev[0]) if hook_ev else 0.0
    if not any(x[0].kind == "dialogue" and x[1] <= 3.0 for x in tl):
        strong_action = (cfg.get("fix_silent_action_hook") and hook_ev is not None
                         and hook_ev[0].kind in ("action", "sfx") and hook >= cfg.get("silent_hook_heat", 0.5))
        if not strong_action:
            hook *= 0.75  # silent opening: weaker on social feeds
    first_line = talk[0][0] if talk else None
    flags = []
    if first_line is not None and talk[0][1] <= 3.5:
        if CONTINUATION.match(first_line.text.strip()) or first_line.offscreen:
            hook *= 0.6
            flags.append("opens mid-sentence / on an off-screen line")
    if c.kind == "cold_open":
        hook = max(hook, line_heat(c.features["_hook_event"]))

    # ---------- cliffhanger: last beat ----------
    last_seg = c.segments[-1]
    ep = eps[last_seg.episode]
    tail = [x for x in tl if x[2] >= dur - 6.0]
    tail_text = " ".join(x[0].text for x in tail if x[0].kind != "camera")
    tail_tone = " ".join(x[0].tone for x in tail)
    last_line = talk[-1][0] if talk else None
    cliff = 0.0
    if last_line is not None and talk[-1][2] >= dur - 8.0:
        lt = last_line.text.strip()
        if lt.endswith("?"):
            cliff += 0.25
        if lt.endswith("...") or lt.endswith("…"):
            cliff += 0.15
    tail_beats = [x for x in tail if x[0].kind in ("dialogue", "action")]
    cliff += 0.30 * max((line_heat(x[0]) for x in tail_beats), default=0.0)
    visual = " ".join(x[0].text + " " + x[0].tone for x in tail)   # camera + sfx included
    cliff += 0.15 * min(1, rx(CLIFF_SFX, visual))
    cliff += 0.05 * min(1, rx(PHYSICAL, tail_text))
    if cfg.get("fix_late_window"):
        # A big beat a few seconds before the cut (explosion, entrance, reveal) still leaves the viewer hanging.
        win = cfg.get("late_window_s", 12.0)
        late = [x for x in tl if dur - win <= x[2] < dur - 6.0]
        late_text = " ".join(x[0].text + " " + x[0].tone for x in late)
        cliff += cfg.get("late_window_weight", 0.10) * min(1, rx(LATE_BEAT + "|" + PHYSICAL, late_text))
    nxt = [e for e in ep.lines if e.start >= last_seg.end - 0.1]
    if nxt and last_line is not None and nxt[0].speaker != last_line.speaker:
        cliff += 0.10
    is_finale = last_seg.end >= ep.duration - 1.0
    if is_finale:
        cliff += cfg.get("finale_bonus", 0.20)   # writers already placed a cliffhanger here
    if cfg.get("fix_calm_delivery"):
        tone_clean = re.sub(DELIVERY, " ", tail_tone.lower())
        calm = rx(CALM, tail_text) + rx(CALM, tone_clean)
    else:
        calm = rx(CALM, tail_text + " " + tail_tone)
    if calm:
        cliff -= 0.12 * min(2, calm)
        flags.append("ends on a calm / resolved beat")
    cliff = max(0.0, min(1.0, cliff))

    # ---------- standalone: would a stranger follow it ----------
    all_text = " ".join(x[0].text for x in tl).lower()
    anchors = rx(r"sister|father|mother|husband|wife|wedding|marry|bride|groom|family|daughter|soldier|"
                 r"veteran|lady|constable|my lord", all_text)
    standalone = 0.55 + 0.08 * min(4, anchors)
    if rx(r"\bagain\b|last time|that ring|the ledger|the watch", all_text):
        standalone -= 0.10
    if "opens mid-sentence / on an off-screen line" in flags:
        standalone -= 0.15
    depth = cfg.get("episode_depth_penalty", 0.006) * max(0, last_seg.episode - 1)
    if len(talk) < 3:
        standalone -= 0.15
        flags.append("very little dialogue: hard to follow without context")
    standalone_nodepth = max(0.0, min(1.0, standalone))
    standalone = max(0.0, min(1.0, standalone - depth))

    # ---------- heat & length ----------
    heat = sum(line_heat(x[0]) for x in beats) / max(1.0, dur / 4.0)
    heat = min(1.0, heat / 2.0)
    ideal = cfg.get("ideal_length", 38)
    length = math.exp(-((dur - ideal) / 14.0) ** 2)

    w = cfg["weights"]
    score = (w["hook"] * hook + w["cliff"] * cliff + w["standalone"] * standalone
             + w["heat"] * heat + w["length"] * length)
    if c.kind == "cold_open":
        score -= cfg.get("cold_open_penalty", 0.03)   # editing cost: two cuts instead of one

    c.features.update(dict(hook=round(hook, 3), cliff=round(cliff, 3), standalone=round(standalone, 3),
                           standalone_nodepth=round(standalone_nodepth, 3),
                           heat=round(heat, 3), length=round(length, 3), finale=is_finale, flags=flags,
                           hook_line=(hook_ev[0].text if hook_ev else ""),
                           hook_speaker=(hook_ev[0].speaker if hook_ev else ""),
                           cliff_line=(last_line.text if last_line else ""),
                           cliff_speaker=(last_line.speaker if last_line else "")))
    c.score = round(score, 4)
    return c


def transcript(c: Candidate, eps: dict[int, Episode], with_camera=False) -> str:
    """Screenplay excerpt in play order, timestamps relative to the promo."""
    rows = []
    for e, ps, pe in timeline(c, eps):
        if e.kind == "camera" and not with_camera:
            continue
        if e.kind == "dialogue":
            rows.append(f"[{ps:05.1f}s] {e.speaker}{' (O.S.)' if e.offscreen else ''} ({e.tone}): \"{e.text}\"")
        else:
            rows.append(f"[{ps:05.1f}s] {e.kind.upper()}: {e.text}")
    return "\n".join(rows)

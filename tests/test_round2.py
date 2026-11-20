"""Round 2: one test per rule fix (a to e), judge v2 parsing, and the stop guards. Invented text only."""
import copy

import pytest

from promo_finder.candidates import Candidate, Segment
from promo_finder.features import score_candidate
from promo_finder.judge import (PROMPT_VERSION_V2, StopJudging, build_prompt, judge, parse_judge_output)
from promo_finder.llm import LLMError
from promo_finder.parser import parse_episode
from promo_finder.pipeline import qa, rules_for_blend, set_finals


def tc(sec):
    m, s = divmod(sec, 60)
    return f"{int(m):02d}:{s:05.2f}"


def episode(tmp_path, beats, number=1, seconds=40.0):
    """beats: list of (start, end, LABEL, text). A camera shot every 4 s is added."""
    out = [f"EPISODE NUMBER: Episode {number}", "EPISODE LOGLINE: A clerk is accused of theft.",
           "CONTINUITY NOTES: Follows the trial.", "", "SCENE 01", ""]
    t = 0.0
    while t + 4 <= seconds + 1e-6:
        out += ["**CAMERA:**", f"Start: ({tc(t)}) | End: ({tc(t + 4)})", f"Shot at {t:.0f} s.", ""]
        t += 4
    for a, b, label, text in beats:
        out += [f"**{label}:**", f"Start: ({tc(a)}) | End: ({tc(b)})", text, ""]
    p = tmp_path / f"ep{number}.txt"
    p.write_text("\n".join(out), encoding="utf-8")
    ep = parse_episode(p)
    return {ep.number: ep}


def clip(eps, a=0.0, b=36.0):
    return Candidate("single", [Segment(1, a, b)])


def scored(cfg, eps, c, **flags):
    sc = copy.deepcopy(cfg["scoring"])
    for k in ("fix_late_window", "fix_depth_once", "fix_silent_action_hook", "fix_calm_delivery"):
        sc[k] = False
    sc.update(flags)
    c.features = {}
    score_candidate(c, eps, sc)
    return c


QUIET = [(1.0, 3.0, "ANNA (Cold)", "You knew."), (5, 8, "BEN (Quiet)", "I did."), (9, 12, "ANNA (Cold)", "Why?"),
         (14, 17, "BEN (Flat)", "Because I had to."), (31.0, 34.0, "ANNA (Low)", "Then go.")]


def test_a_late_window_credits_a_big_beat_before_the_cut(cfg, tmp_path):
    eps = episode(tmp_path, QUIET + [(26.0, 27.5, "ACTION", "The doors explode inward and armed men storm in.")])
    off = scored(cfg, eps, clip(eps)).features["cliff"]
    on = scored(cfg, eps, clip(eps), fix_late_window=True).features["cliff"]
    assert on > off


def test_b_depth_penalty_counted_once_when_llm_judged(cfg, tmp_path):
    eps = episode(tmp_path, QUIET, number=30)
    c = Candidate("single", [Segment(30, 0.0, 36.0)])
    cfg = copy.deepcopy(cfg)
    cfg["scoring"]["fix_depth_once"] = True
    score_candidate(c, eps, cfg["scoring"])
    assert c.features["standalone_nodepth"] > c.features["standalone"]       # depth penalty applied
    assert rules_for_blend(c, cfg) == c.score                                 # no LLM yet: unchanged
    c.llm = {"standalone_score": 6}
    assert rules_for_blend(c, cfg) > c.score                                  # LLM judged: penalty dropped
    cfg["scoring"]["fix_depth_once"] = False
    assert rules_for_blend(c, cfg) == c.score


def test_c_strong_silent_action_opening_keeps_its_hook(cfg, tmp_path):
    beats = [(0.2, 2.5, "ACTION", "He smashes the door and shoves the guard to the floor!")] + QUIET[1:]
    eps = episode(tmp_path, beats)
    off = scored(cfg, eps, clip(eps)).features["hook"]
    on = scored(cfg, eps, clip(eps), fix_silent_action_hook=True).features["hook"]
    assert on > off and on == pytest.approx(off / 0.75, abs=0.002)


def test_d_soft_delivery_is_not_a_resolved_ending_but_real_words_are(cfg, tmp_path):
    soft = QUIET[:-1] + [(31.0, 34.0, "ANNA (Soft, Tender)", "Then tell me who you really are.")]
    eps = episode(tmp_path, soft)
    assert "ends on a calm / resolved beat" in scored(cfg, eps, clip(eps)).features["flags"]
    assert "ends on a calm / resolved beat" not in scored(cfg, eps, clip(eps), fix_calm_delivery=True).features["flags"]
    real = QUIET[:-1] + [(31.0, 34.0, "ANNA (Soft)", "Thank you. It is over now.")]
    eps2 = episode(tmp_path, real, number=2)
    c = Candidate("single", [Segment(2, 0.0, 36.0)])
    assert "ends on a calm / resolved beat" in scored(cfg, eps2, c, fix_calm_delivery=True).features["flags"]


def test_e_resolved_ending_cannot_outrank_open_endings(cfg):
    cfg = copy.deepcopy(cfg)
    cfg["ranking"]["fix_cap_resolved"] = True
    llm = {"hook_score": 9, "standalone_score": 8, "overall": 8}
    resolved = Candidate("single", [Segment(1, 0, 30)], features={"flags": ["ends on a calm / resolved beat"]},
                         score=0.9, llm={**llm, "cliffhanger_score": 4})
    open_end = Candidate("single", [Segment(2, 0, 30)], features={"flags": []}, score=0.3,
                         llm={**llm, "cliffhanger_score": 4, "hook_score": 3, "overall": 3})
    high_cliff = Candidate("single", [Segment(3, 0, 30)], features={"flags": ["ends on a calm / resolved beat"]},
                           score=0.9, llm={**llm, "cliffhanger_score": 8})     # LLM disagrees: not capped
    set_finals([resolved, open_end, high_cliff], cfg)
    assert resolved.final < open_end.final
    assert high_cliff.final > open_end.final


def test_v2_parsing_normalises_types():
    out = parse_judge_output({"hook_score": "8", "cliffhanger_score": 12, "standalone_score": None,
                              "overall": "7.5", "needs_prior_context": "true", "context_reason": "who is he"}, "v2")
    assert out["hook_score"] == 8.0 and out["cliffhanger_score"] == 10.0 and out["standalone_score"] == 0.0
    assert out["overall"] == 7.5 and out["needs_prior_context"] is True
    assert out["prompt_version"] == PROMPT_VERSION_V2
    assert parse_judge_output({"needs_prior_context": False}, "v2")["needs_prior_context"] is False
    assert parse_judge_output({"needs_prior_context": "no"}, "v2")["needs_prior_context"] is False
    assert "needs_prior_context" not in parse_judge_output({"overall": 5}, "v1")


def test_v2_prompt_has_summary_and_version(tmp_path):
    eps = episode(tmp_path, QUIET)
    system, user = build_prompt(clip(eps), eps, "v2")
    assert PROMPT_VERSION_V2 in system and "romantic or visual" in system
    assert user.startswith("EPISODE SUMMARY: A clerk is accused of theft. Follows the trial.")
    assert "needs_prior_context" in user and "confusing_for_new_viewer" not in user
    s1, _ = build_prompt(clip(eps), eps, "v1")
    assert s1 != system                                    # different prompt, different cache key


def test_qa_uses_the_v2_flag(cfg):
    c = Candidate("single", [Segment(1, 0.0, 30.0)], score=0.6,
                  features={"hook": 0.8, "cliff": 0.7, "standalone": 0.8, "flags": []})

    class Ep:
        lines, duration = [], 100.0

    base = {"hook_score": 8, "cliffhanger_score": 8, "standalone_score": 7, "overall": 6}
    c.llm = {**base, "needs_prior_context": False, "context_reason": ""}
    assert qa(c, {1: Ep()}, cfg)["confidence"] == "high"
    c.llm = {**base, "needs_prior_context": True, "context_reason": "who is the stranger"}
    q = qa(c, {1: Ep()}, cfg)
    assert q["confidence"] == "medium" and "needs prior context" in q["issues"][0]


class FakeLLM:
    def __init__(self, fail_at=None, tokens=0, budget=0):
        self.calls = self.tokens_in = self.tokens_out = 0
        self.fail_at, self.per_call, self.max_run_tokens = fail_at, tokens, budget

    def complete_json(self, system, user):
        if self.fail_at and self.calls + 1 == self.fail_at:
            raise LLMError("groq 429: rate_limit_exceeded tokens per day")
        self.calls += 1
        self.tokens_in += self.per_call
        return {"hook_score": 5, "cliffhanger_score": 5, "standalone_score": 5, "overall": 5,
                "needs_prior_context": False}


def test_judge_stops_on_first_429_without_looping(tmp_path):
    eps = episode(tmp_path, QUIET)
    cands = [clip(eps) for _ in range(5)]
    llm = FakeLLM(fail_at=3)
    with pytest.raises(StopJudging):
        judge(cands, eps, llm, log=lambda *a: None, version="v2")
    assert llm.calls == 2                                    # no call after the 429
    assert all("error" in c.llm for c in cands[2:])


def test_judge_stops_before_the_token_budget(tmp_path):
    eps = episode(tmp_path, QUIET)
    cands = [clip(eps) for _ in range(10)]
    llm = FakeLLM(tokens=1000, budget=3500)
    with pytest.raises(StopJudging):
        judge(cands, eps, llm, log=lambda *a: None, version="v2")
    assert llm.calls == 3 and llm.tokens_in <= 3500

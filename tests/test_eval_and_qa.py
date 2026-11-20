import json

import pytest
from evaluate import evaluate, match, shared

from promo_finder.candidates import Candidate, Segment
from promo_finder.pipeline import qa


def seg(ep, a, b):
    return {"episode": ep, "start": a, "end": b, "start_tc": "", "end_tc": ""}


def test_overlap_math():
    g = {"episode": 3, "start": 10.0, "end": 40.0}
    assert shared([seg(3, 20, 50)], g) == pytest.approx(20.0)
    assert shared([seg(4, 20, 50)], g) == 0.0                     # other episode never counts
    assert match({"segments": [seg(3, 20, 50)]}, g)               # 20 s of a 30 s shorter clip
    assert not match({"segments": [seg(3, 30, 70)]}, g)           # 10 s of 30 s: below half
    # cold open: both segments count toward the shared time
    assert match({"segments": [seg(3, 38, 40), seg(3, 10, 22)]}, g)


def test_recall_precision_and_split(tmp_path):
    promos = {"meta": {"model": "test"}, "promos": [
        {"post_rank": 1, "segments": [seg(1, 0, 30)], "hook": "", "cliffhanger": ""},
        {"post_rank": 2, "segments": [seg(2, 0, 30)], "hook": "", "cliffhanger": ""},
        {"post_rank": 3, "segments": [seg(3, 50, 80)], "hook": "", "cliffhanger": ""},
    ]}
    pj = tmp_path / "promos.json"
    pj.write_text(json.dumps(promos), encoding="utf-8")
    gold = tmp_path / "gold.yaml"
    gold.write_text("- {id: G01, episode: 1, start: 5, end: 30, why: a}\n"
                    "- {id: G02, episode: 3, start: 0, end: 30, why: b}\n", encoding="utf-8")
    r = evaluate(str(pj), str(gold), 3, covered={1, 2, 3})
    assert (r["found"], r["gold"], r["hits"], r["graded"]) == (1, 2, 1, 3)
    odd = evaluate(str(pj), str(gold), 3, episodes={1, 3}, covered={1, 2, 3})
    assert (odd["found"], odd["gold"], odd["graded"]) == (1, 2, 2)  # episode 2 pick left out


@pytest.fixture
def clip():
    c = Candidate("single", [Segment(1, 0.0, 30.0)])
    c.score = 0.60
    c.features = {"hook": 0.8, "cliff": 0.7, "standalone": 0.8, "flags": []}
    return c


class FakeEp:
    lines = []
    duration = 100.0


def judged(clip, **llm):
    base = {"hook_score": 8, "cliffhanger_score": 8, "standalone_score": 7, "overall": 6,
            "confusing_for_new_viewer": ""}
    base.update(llm)
    clip.llm = base
    return clip


def test_qa_high_when_no_flags(clip, cfg):
    q = qa(judged(clip), {1: FakeEp()}, cfg)
    assert q["confidence"] == "high" and q["issues"] == []


@pytest.mark.parametrize("llm, reason", [
    ({"confusing_for_new_viewer": "who is she?"}, "confusing for a new viewer"),
    ({"standalone_score": 4}, "standalone score 4/10 is below 5"),
    ({"overall": 1}, "rules and LLM disagree"),
])
def test_qa_each_flag_gives_medium(clip, cfg, llm, reason):
    q = qa(judged(clip, **llm), {1: FakeEp()}, cfg)
    assert q["confidence"] == "medium"
    assert any(reason in i for i in q["issues"])


def test_qa_confusing_text_can_be_switched_off(clip, cfg):
    cfg["qa"]["flag_on_confusing_text"] = False
    q = qa(judged(clip, confusing_for_new_viewer="who is she?"), {1: FakeEp()}, cfg)
    assert q["confidence"] == "high"


def test_qa_hard_fail_is_low(clip, cfg):
    clip.segments = [Segment(1, 0.0, 75.0)]                       # longer than 60 s
    q = qa(judged(clip), {1: FakeEp()}, cfg)
    assert q["confidence"] == "low" and "length_20_60s" in q["issues"]

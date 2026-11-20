from conftest import screenplay

from promo_finder.parser import load_show, parse_episode


def test_event_count_on_sample(tmp_path):
    p = tmp_path / "episode_007.txt"
    p.write_text(screenplay(7, seconds=96.0), encoding="utf-8")
    ep = parse_episode(p)
    # 24 shots of 4 s, each with one camera event and one beat
    assert ep.number == 7
    assert len(ep.events) == 48
    assert len(ep.shots) == 24
    assert len(ep.lines) == 18          # 9 of every 12 beats in the sample are dialogue
    assert ep.duration == 96.0
    assert ep.warnings == []


def test_malformed_input_warns_and_does_not_crash(tmp_path):
    d = tmp_path / "messy"
    d.mkdir()
    good = screenplay(2)
    # malformed timing line in one block
    bad = good.replace("Start: (00:04.50)", "Start: (00:0x.50)", 1)
    (d / "z_second.txt").write_text(bad, encoding="utf-8")
    # no header, number only in a messy file name, extra blank lines, byte-order mark
    noheader = screenplay(None, header=False).replace("**\nStart:", "**\n\n\nStart:").replace(")\n", ")\n\n")
    (d / "Show S1 - EP05 FINAL v2.txt").write_text("﻿\n\n" + noheader, encoding="utf-8")
    # a file that is not a screenplay at all
    (d / "notes.txt").write_text("just some notes\n", encoding="utf-8")

    show = load_show(d)
    assert [e.number for e in show] == [2, 5]
    warns = " | ".join(w for e in show for w in e.warnings)
    assert "line" in warns and "no valid 'Start" in warns            # the malformed block is named
    assert "took episode 5 from the file name" in warns
    assert "episode numbers missing from the input: [3, 4]" in warns
    assert "notes.txt: no events found" in warns
    ep5 = [e for e in show if e.number == 5][0]
    assert len(ep5.events) == 48                                     # blank lines did not lose text
    assert all(e.text for e in ep5.events)
    ep2 = [e for e in show if e.number == 2][0]
    assert len(ep2.events) == 47                                     # exactly one block skipped


def test_duplicate_episode_numbers_keep_the_first(tmp_path):
    d = tmp_path / "dup"
    d.mkdir()
    (d / "a.txt").write_text(screenplay(4), encoding="utf-8")
    (d / "b.txt").write_text(screenplay(4), encoding="utf-8")
    show = load_show(d)
    assert len(show) == 1
    assert any("already loaded from a.txt" in w for w in show[0].warnings)

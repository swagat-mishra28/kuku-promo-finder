from promo_finder.candidates import _straddles, cold_open_candidates, hook_clips, single_candidates
from promo_finder.features import score_candidate
from promo_finder.parser import load_show


def test_cuts_are_20_to_60_s_and_never_mid_dialogue(show_dir):
    eps = load_show(show_dir)
    for ep in eps:
        cands = single_candidates(ep, 20, 60)
        assert cands, "sample episode should produce legal cuts"
        for c in cands:
            assert 20 <= c.duration <= 60
            s = c.segments[0]
            assert not _straddles(ep, s.start)
            assert not _straddles(ep, s.end)


def test_cold_open_hook_is_the_payoff_within_max_gap(show_dir, cfg):
    eps_list = load_show(show_dir)
    eps = {e.number: e for e in eps_list}
    singles = [c for ep in eps_list for c in single_candidates(ep, 20, 60)]
    for c in singles:
        score_candidate(c, eps, cfg["scoring"])
    hooks = {ep.number: hook_clips(ep) for ep in eps_list}
    max_gap = 25.0
    colds = cold_open_candidates(eps, singles, hooks, 20, 60, top_bodies=200, max_gap=max_gap)
    assert colds
    for c in colds:
        hook, body = c.segments
        assert 20 <= c.duration <= 60
        if hook.episode == body.episode:
            gap = hook.start - body.end
            assert 0.5 <= gap <= max_gap          # flash comes from just after the body ends
        else:
            assert hook.episode == body.episode + 1
            assert body.end >= eps[body.episode].duration - 1.0   # body ends on the episode's last beat
            assert hook.start <= max_gap

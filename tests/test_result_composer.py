from app.domain.result_composer import TextFragment, clamp_percent, deterministic_pick


def test_deterministic_pick_is_reproducible() -> None:
    fragments = [TextFragment("a", "A"), TextFragment("b", "B"), TextFragment("c", "C")]
    first = deterministic_pick(fragments, "session-1:content-v1", "opening")
    second = deterministic_pick(fragments, "session-1:content-v1", "opening")
    assert first == second


def test_percent_is_clamped() -> None:
    assert clamp_percent(-4.5) == 0
    assert clamp_percent(82.4) == 82
    assert clamp_percent(140) == 100


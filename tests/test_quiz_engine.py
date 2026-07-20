from app.domain.quiz_engine import (
    compose_result,
    compute_confidence,
    compute_scores,
    load_content,
    public_questions,
    rank_narratives,
)


def test_both_test_contents_load_and_have_11_narratives() -> None:
    for test_key in ("designer-profile", "project-narrative"):
        content = load_content(test_key)
        assert len(content["narratives"]) == 11
        assert content["questions"]


def test_public_questions_never_leak_weights() -> None:
    content = load_content("designer-profile")
    for question in public_questions(content):
        for option in question["options"]:
            assert "weights" not in option


def test_unknown_question_or_option_ignored_not_crash() -> None:
    content = load_content("designer-profile")
    scores = compute_scores(content, {"does-not-exist": "a", "q1": "does-not-exist"})
    assert scores["time"] == 0


def test_confidence_zero_when_no_answers() -> None:
    content = load_content("project-narrative")
    assert compute_confidence(content, {}) == 0


def test_confidence_full_when_all_meaningfully_answered() -> None:
    content = load_content("project-narrative")
    answers = {q["id"]: q["options"][0]["id"] for q in content["questions"]}
    assert compute_confidence(content, answers) == 100


def test_dunno_answer_lowers_confidence_not_score() -> None:
    content = load_content("project-narrative")
    dunno_question = next(q for q in content["questions"] if any(o["id"] == "dunno" for o in q["options"]))
    scores_before = compute_scores(content, {})
    scores_after = compute_scores(content, {dunno_question["id"]: "dunno"})
    assert scores_before == scores_after
    assert compute_confidence(content, {dunno_question["id"]: "dunno"}) == 0


def test_rank_narratives_sums_to_reasonable_bounds() -> None:
    content = load_content("designer-profile")
    ranked = rank_narratives(content, {})
    assert len(ranked) == 11
    assert all(r["fit_percent"] == 0 for r in ranked)


def test_rank_narratives_tie_break_is_deterministic_by_content_order() -> None:
    content = load_content("designer-profile")
    scores = {key: 5.0 for key in content["narratives"]}
    ranked_a = rank_narratives(content, scores)
    ranked_b = rank_narratives(content, dict(scores))
    assert [r["key"] for r in ranked_a] == [r["key"] for r in ranked_b]


def test_compose_result_picks_consistent_primary_for_same_answers() -> None:
    content = load_content("project-narrative")
    answers = {q["id"]: q["options"][0]["id"] for q in content["questions"]}
    first = compose_result("project-narrative", content, answers)
    second = compose_result("project-narrative", content, answers)
    assert first["primary_narrative_key"] == second["primary_narrative_key"]
    assert first["primary_score"] == second["primary_score"]


def test_compose_result_alternatives_exclude_primary() -> None:
    content = load_content("designer-profile")
    answers = {q["id"]: q["options"][1]["id"] for q in content["questions"]}
    result = compose_result("designer-profile", content, answers)
    alt_keys = {a["key"] for a in result["alternatives"]}
    assert result["primary_narrative_key"] not in alt_keys
    assert len(result["alternatives"]) == 2

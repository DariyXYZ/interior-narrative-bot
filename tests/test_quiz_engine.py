from app.domain.quiz_engine import (
    compose_result,
    compute_confidence,
    compute_scores,
    load_content,
    load_phrase_bank,
    narrative_detail_for_session,
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
        assert "multi" in question
        for option in question["options"]:
            assert "weights" not in option


def test_unknown_question_or_option_ignored_not_crash() -> None:
    content = load_content("designer-profile")
    scores = compute_scores(content, {"does-not-exist": ["a"], "q1": ["does-not-exist"]})
    assert scores["time"] == 0


def test_confidence_zero_when_no_answers() -> None:
    content = load_content("project-narrative")
    assert compute_confidence(content, {}) == 0


def test_confidence_full_when_all_meaningfully_answered() -> None:
    content = load_content("project-narrative")
    answers = {q["id"]: [q["options"][0]["id"]] for q in content["questions"]}
    assert compute_confidence(content, answers) == 100


def test_dunno_answer_lowers_confidence_not_score() -> None:
    content = load_content("project-narrative")
    dunno_question = next(q for q in content["questions"] if any(o["id"] == "dunno" for o in q["options"]))
    scores_before = compute_scores(content, {})
    scores_after = compute_scores(content, {dunno_question["id"]: ["dunno"]})
    assert scores_before == scores_after
    assert compute_confidence(content, {dunno_question["id"]: ["dunno"]}) == 0


def test_multi_select_combines_different_keys_from_several_options() -> None:
    content = load_content("project-narrative")
    multi_question = next(q for q in content["questions"] if q["multi"] and len(q["options"]) >= 2)
    opt_a, opt_b = multi_question["options"][0], multi_question["options"][1]
    scores_a = compute_scores(content, {multi_question["id"]: [opt_a["id"]]})
    scores_both = compute_scores(content, {multi_question["id"]: [opt_a["id"], opt_b["id"]]})
    # выбор второго варианта не может УМЕНЬШИТЬ ни один счёт, набранный первым
    for key, value in scores_a.items():
        assert scores_both[key] >= value


def test_multi_select_same_key_from_two_options_does_not_double_count() -> None:
    content = load_content("project-narrative")
    # ищем вопрос, где хотя бы два варианта указывают на один и тот же ключ
    target = None
    for question in content["questions"]:
        if not question["multi"]:
            continue
        seen: dict[str, list[float]] = {}
        for option in question["options"]:
            for key, weight in option.get("weights", {}).items():
                seen.setdefault(key, []).append(weight)
        for key, weights in seen.items():
            if len(weights) >= 2:
                target = (question, key, max(weights))
                break
        if target:
            break
    assert target is not None, "в контенте должен быть хотя бы один такой multi-вопрос"
    question, key, expected_max = target
    all_ids = [o["id"] for o in question["options"] if key in o.get("weights", {})]
    scores = compute_scores(content, {question["id"]: all_ids})
    assert scores[key] == expected_max


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
    answers = {q["id"]: [q["options"][0]["id"]] for q in content["questions"]}
    first = compose_result("project-narrative", content, answers, "session-a")
    second = compose_result("project-narrative", content, answers, "session-a")
    assert first["primary_narrative_key"] == second["primary_narrative_key"]
    assert first["primary_score"] == second["primary_score"]
    assert first["result_text"] == second["result_text"]
    assert first["fragment_ids"] == second["fragment_ids"]


def test_compose_result_alternatives_exclude_primary() -> None:
    content = load_content("designer-profile")
    answers = {q["id"]: [q["options"][1]["id"]] for q in content["questions"]}
    result = compose_result("designer-profile", content, answers, "session-b")
    alt_keys = {a["key"] for a in result["alternatives"]}
    assert result["primary_narrative_key"] not in alt_keys
    assert len(result["alternatives"]) == 2


def test_phrase_bank_gives_varied_result_text_across_sessions() -> None:
    content = load_content("project-narrative")
    answers = {q["id"]: [q["options"][0]["id"]] for q in content["questions"]}
    texts = {
        compose_result("project-narrative", content, answers, f"session-{i}")["result_text"]
        for i in range(8)
    }
    # разные сессии с одним и тем же ответом должны получать не один и тот же текст всегда
    assert len(texts) > 1


def test_narrative_detail_for_session_is_deterministic_and_uses_phrase_bank() -> None:
    content = load_content("project-narrative")
    phrase_bank = load_phrase_bank()
    key = next(iter(content["narratives"]))
    first = narrative_detail_for_session(content, phrase_bank, key, "fixed-session")
    second = narrative_detail_for_session(content, phrase_bank, key, "fixed-session")
    assert first == second
    assert first["fragment_ids"]
    for fragment_id in first["fragment_ids"]:
        assert fragment_id.startswith(f"{key}.")


# ─── Типологические формулировки (variants) ───

# Типологии из <select id="project-object-type"> в webapp/index.html, кроме «other».
TYPOLOGIES = ("office", "restaurant", "hotel", "residential-common", "airport", "museum")


def test_variants_only_override_text_never_structure() -> None:
    """Подмена по типологии — только слова: id опций, multi и веса остаются базовыми,
    иначе scoring разъехался бы между типологиями."""
    content = load_content("project-narrative")
    base = public_questions(content)
    for typology in TYPOLOGIES:
        typed = public_questions(content, typology)
        assert [q["id"] for q in typed] == [q["id"] for q in base]
        for q_base, q_typed in zip(base, typed):
            assert q_typed["multi"] == q_base["multi"]
            assert [o["id"] for o in q_typed["options"]] == [o["id"] for o in q_base["options"]]
            for option in q_typed["options"]:
                assert "weights" not in option


def test_variants_reference_only_existing_options_and_leave_dunno_alone() -> None:
    content = load_content("project-narrative")
    for question in content["questions"]:
        valid = {o["id"] for o in question["options"]}
        for typology, variant in (question.get("variants") or {}).items():
            assert typology in TYPOLOGIES, f"{question['id']}: неизвестная типология {typology}"
            assert variant.get("text"), f"{question['id']}/{typology}: пустой текст"
            unknown = set(variant.get("options") or {}) - valid
            assert not unknown, f"{question['id']}/{typology}: опции {unknown} не существуют"
            assert "dunno" not in (variant.get("options") or {})


def test_each_typology_rewords_at_least_60_percent_of_questions() -> None:
    """Продуктовое требование: пройдя тест для офиса и для музея, человек должен
    видеть, что тест подстроился под типологию."""
    content = load_content("project-narrative")
    base = {q["id"]: q["text"] for q in public_questions(content)}
    for typology in TYPOLOGIES:
        reworded = sum(1 for q in public_questions(content, typology) if q["text"] != base[q["id"]])
        assert reworded / len(base) >= 0.6, f"{typology}: {reworded}/{len(base)}"


def test_unknown_or_missing_typology_falls_back_to_base_wording() -> None:
    content = load_content("project-narrative")
    base = public_questions(content)
    assert public_questions(content, None) == base
    assert public_questions(content, "other") == base
    assert public_questions(content, "spaceship") == base

from __future__ import annotations

import json
from functools import lru_cache

from app.core.config import BASE_DIR

CONTENT_DIR = BASE_DIR / "content"

TEST_CONTENT_FILES = {
    "designer-profile": "designer-profile.v1.json",
    "project-narrative": "project-narrative.v1.json",
}


class ContentNotFoundError(Exception):
    pass


@lru_cache(maxsize=8)
def load_content(test_key: str) -> dict:
    filename = TEST_CONTENT_FILES.get(test_key)
    if not filename:
        raise ContentNotFoundError(f"Неизвестный test_key: {test_key!r}")
    path = CONTENT_DIR / filename
    return json.loads(path.read_text(encoding="utf-8"))


def public_questions(content: dict) -> list[dict]:
    """Вопросы без весов — клиенту веса не отдаём (scoring авторитетен только на сервере)."""
    return [
        {
            "id": q["id"],
            "text": q["text"],
            "options": [{"id": o["id"], "text": o["text"]} for o in q["options"]],
        }
        for q in content["questions"]
    ]


def _question_by_id(content: dict) -> dict[str, dict]:
    return {q["id"]: q for q in content["questions"]}


def compute_scores(content: dict, answers: dict[str, str]) -> dict[str, float]:
    """answers: question_id -> option_id. Неизвестные/отсутствующие вопросы просто не считаются."""
    questions = _question_by_id(content)
    scores = {key: 0.0 for key in content["narratives"]}
    for question_id, option_id in answers.items():
        question = questions.get(question_id)
        if question is None:
            continue
        option = next((o for o in question["options"] if o["id"] == option_id), None)
        if option is None:
            continue
        for key, weight in option.get("weights", {}).items():
            scores[key] = scores.get(key, 0.0) + weight
    return scores


def compute_confidence(content: dict, answers: dict[str, str]) -> int:
    """Доля вопросов с содержательным ответом (не 'не знаю', не пропуск).

    v1: линейная доля отвеченных содержательно вопросов. Дальше можно усложнить
    (противоречия, adaptive-вопросы), но для MVP этого достаточно и это честно
    показывает "мало данных - низкая уверенность", как требуют Product Decisions.
    """
    questions = _question_by_id(content)
    total = len(questions)
    if total == 0:
        return 0
    meaningful = 0
    for question_id, option_id in answers.items():
        question = questions.get(question_id)
        if question is None:
            continue
        option = next((o for o in question["options"] if o["id"] == option_id), None)
        if option and option.get("weights"):
            meaningful += 1
    return round(100 * meaningful / total)


def rank_narratives(content: dict, scores: dict[str, float]) -> list[dict]:
    """Возвращает нарративы, отсортированные по fit% по убыванию.

    Порядок ключей в content['narratives'] (dict, Python 3.7+ сохраняет insertion order)
    - детерминированный tie-break: при равенстве процентов выигрывает тот, что раньше
    объявлен в content, а не порядок из недетерминированного словаря scores.
    """
    ranked = []
    for key, narrative in content["narratives"].items():
        max_score = narrative.get("max_score") or 0.0
        raw = scores.get(key, 0.0)
        fit_percent = round(100 * raw / max_score) if max_score > 0 else 0
        ranked.append({"key": key, "raw_score": raw, "max_score": max_score, "fit_percent": max(0, min(100, fit_percent))})
    ranked.sort(key=lambda item: item["fit_percent"], reverse=True)
    return ranked


def compose_designer_profile_result(content: dict, answers: dict[str, str]) -> dict:
    scores = compute_scores(content, answers)
    ranked = rank_narratives(content, scores)
    confidence = compute_confidence(content, answers)
    top = ranked[0]
    top_n = content["narratives"][top["key"]]
    bottom3 = ranked[-3:]
    bottom3_names = [content["narratives"][r["key"]]["name"] for r in reversed(bottom3)]
    second, third = ranked[1], ranked[2]
    second_name = content["narratives"][second["key"]]["name"]
    third_name = content["narratives"][third["key"]]["name"]

    result_text = (
        f"Ваш ведущий архетип — {top_n['name']} ({top['fit_percent']}% совпадение профиля). "
        f"{top_n['desc']} Его хорошо дополняют {second_name} и {third_name}. "
        f"В профиле меньше — {', '.join(bottom3_names)}: это не дефициты, а инструменты, которые пока реже используются."
    )

    alternatives = [
        {
            "key": r["key"],
            "name": content["narratives"][r["key"]]["name"],
            "subtitle": content["narratives"][r["key"]]["subtitle"],
            "fit_percent": r["fit_percent"],
        }
        for r in ranked[1:3]
    ]

    return {
        "primary_narrative_key": top["key"],
        "primary_score": top["fit_percent"],
        "alternatives": alternatives,
        "confidence": confidence,
        "result_text": result_text,
        "fragment_ids": [],
        "scoring_trace": {"scores": scores, "answers": answers, "ranked": ranked},
    }


def compose_project_narrative_result(content: dict, answers: dict[str, str]) -> dict:
    scores = compute_scores(content, answers)
    ranked = rank_narratives(content, scores)
    confidence = compute_confidence(content, answers)
    top = ranked[0]
    top_n = content["narratives"][top["key"]]
    alternatives = [
        {
            "key": r["key"],
            "name": content["narratives"][r["key"]]["name"],
            "subtitle": content["narratives"][r["key"]]["subtitle"],
            "fit_percent": r["fit_percent"],
        }
        for r in ranked[1:3]
    ]

    confidence_note = (
        "Ответов достаточно, чтобы уверенно опираться на рекомендацию."
        if confidence >= 70
        else "Часть вопросов осталась без ответа — рекомендацию стоит перепроверить после уточнения брифа."
    )

    result_text = (
        f"Рабочая гипотеза для этого проекта — «{top_n['name']}» ({top['fit_percent']}% соответствия). "
        f"{top_n['thesis']} {confidence_note}"
    )

    return {
        "primary_narrative_key": top["key"],
        "primary_score": top["fit_percent"],
        "alternatives": alternatives,
        "confidence": confidence,
        "result_text": result_text,
        "fragment_ids": [],
        "scoring_trace": {"scores": scores, "answers": answers, "ranked": ranked},
    }


RESULT_COMPOSERS = {
    "designer-profile": compose_designer_profile_result,
    "project-narrative": compose_project_narrative_result,
}


def compose_result(test_key: str, content: dict, answers: dict[str, str]) -> dict:
    composer = RESULT_COMPOSERS.get(test_key)
    if composer is None:
        raise ContentNotFoundError(f"Нет result composer для test_key: {test_key!r}")
    return composer(content, answers)


def full_ranking(content: dict, ranked: list[dict]) -> list[dict]:
    """Все нарративы с полной карточкой (для колеса и развёрнутого списка), не только топ-3."""
    result = []
    for item in ranked:
        detail = narrative_detail(content, item["key"])
        result.append({**detail, "fit_percent": item["fit_percent"]})
    return result


def narrative_detail(content: dict, key: str) -> dict:
    """Полная карточка нарратива для экрана результата (без max_score - внутренняя деталь)."""
    n = dict(content["narratives"][key])
    n.pop("max_score", None)
    n["key"] = key
    if content["test_key"] == "designer-profile":
        n["advice"] = content.get("advice", {}).get(key)
    return n

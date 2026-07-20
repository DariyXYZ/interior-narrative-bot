from __future__ import annotations

import json
from functools import lru_cache

from app.core.config import BASE_DIR
from app.domain.result_composer import TextFragment, clamp_percent, deterministic_pick

CONTENT_DIR = BASE_DIR / "content"

TEST_CONTENT_FILES = {
    "designer-profile": "designer-profile.v1.json",
    "project-narrative": "project-narrative.v1.json",
}

PHRASE_BANK_FILE = "result-phrases.v1.json"

# слот банка фраз -> поле нарратива в project-narrative.v1.json, которое даёт variant "a"
_SLOT_TO_CONTENT_FIELD = {
    "fit_reason": "thesis",
    "client_argument": "client_argument",
    "visual_direction": "visual_direction",
    "risk": "risks",
    "next_step": "next_step",
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


@lru_cache(maxsize=1)
def load_phrase_bank() -> dict:
    path = CONTENT_DIR / PHRASE_BANK_FILE
    return json.loads(path.read_text(encoding="utf-8"))


def public_questions(content: dict) -> list[dict]:
    """Вопросы без весов — клиенту веса не отдаём (scoring авторитетен только на сервере)."""
    return [
        {
            "id": q["id"],
            "text": q["text"],
            "multi": q.get("multi", False),
            "options": [{"id": o["id"], "text": o["text"]} for o in q["options"]],
        }
        for q in content["questions"]
    ]


def _question_by_id(content: dict) -> dict[str, dict]:
    return {q["id"]: q for q in content["questions"]}


def _combined_weights(question: dict, option_ids: list[str]) -> dict[str, float]:
    """Несколько выбранных вариантов на один вопрос (multi-select) — максимум по
    каждому ключу среди выбранных, а не сумма: выбор двух опций, указывающих на
    один и тот же нарратив, не должен давать двойной вес (потолок остаётся тем
    же, что и при одиночном выборе — max_score ниже пересчитывать не нужно),
    но опции, указывающие на РАЗНЫЕ нарративы, обе честно засчитываются."""
    combined: dict[str, float] = {}
    for option_id in option_ids:
        option = next((o for o in question["options"] if o["id"] == option_id), None)
        if option is None:
            continue
        for key, weight in option.get("weights", {}).items():
            combined[key] = max(combined.get(key, 0.0), weight)
    return combined


def compute_scores(content: dict, answers: dict[str, list[str]]) -> dict[str, float]:
    """answers: question_id -> [option_id, ...]. Неизвестные вопросы/варианты игнорируются."""
    questions = _question_by_id(content)
    scores = {key: 0.0 for key in content["narratives"]}
    for question_id, option_ids in answers.items():
        question = questions.get(question_id)
        if question is None:
            continue
        for key, weight in _combined_weights(question, option_ids).items():
            scores[key] = scores.get(key, 0.0) + weight
    return scores


def compute_confidence(content: dict, answers: dict[str, list[str]]) -> int:
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
    for question_id, option_ids in answers.items():
        question = questions.get(question_id)
        if question is None:
            continue
        if _combined_weights(question, option_ids):
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
        fit_percent = clamp_percent(100 * raw / max_score) if max_score > 0 else 0
        ranked.append({"key": key, "raw_score": raw, "max_score": max_score, "fit_percent": fit_percent})
    ranked.sort(key=lambda item: item["fit_percent"], reverse=True)
    return ranked


def _pick_narrative_fragment(content: dict, phrase_bank: dict, key: str, slot: str, session_id: str) -> TextFragment:
    field = _SLOT_TO_CONTENT_FIELD[slot]
    fragments = [TextFragment(id=f"{key}.{slot}.a", text=content["narratives"][key][field])]
    variant_b_text = phrase_bank["slots"][slot].get(key)
    if variant_b_text:
        fragments.append(TextFragment(id=f"{key}.{slot}.b", text=variant_b_text))
    return deterministic_pick(fragments, seed=session_id, slot=f"{slot}:{key}")


def _pick_opening(phrase_bank: dict, session_id: str) -> TextFragment:
    fragments = [TextFragment(id=f["id"], text=f["text"]) for f in phrase_bank["slots"]["opening"]]
    return deterministic_pick(fragments, seed=session_id, slot="opening")


def narrative_detail_for_session(content: dict, phrase_bank: dict, key: str, session_id: str) -> dict:
    """Карточка нарратива для экрана результата с фразами из банка формулировок,
    выбранными детерминированно по session_id — тот же сеанс всегда видит тот же
    текст (воспроизводимо), а разные сеансы с одинаковым primary получают разные
    формулировки одного и того же факта."""
    n = narrative_detail(content, key)
    fragment_ids = []
    for slot, field in _SLOT_TO_CONTENT_FIELD.items():
        picked = _pick_narrative_fragment(content, phrase_bank, key, slot, session_id)
        n[field] = picked.text
        fragment_ids.append(picked.id)
    n["fragment_ids"] = fragment_ids
    return n


def compose_designer_profile_result(content: dict, answers: dict[str, str], session_id: str) -> dict:
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


def compose_project_narrative_result(content: dict, answers: dict[str, str], session_id: str) -> dict:
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

    phrase_bank = load_phrase_bank()
    opening = _pick_opening(phrase_bank, session_id)
    detail = narrative_detail_for_session(content, phrase_bank, top["key"], session_id)

    result_text = (
        f"{opening.text} — «{top_n['name']}» ({top['fit_percent']}% соответствия). "
        f"{detail['thesis']} {confidence_note}"
    )

    return {
        "primary_narrative_key": top["key"],
        "primary_score": top["fit_percent"],
        "alternatives": alternatives,
        "confidence": confidence,
        "result_text": result_text,
        "fragment_ids": [opening.id] + detail["fragment_ids"],
        "scoring_trace": {"scores": scores, "answers": answers, "ranked": ranked},
    }


RESULT_COMPOSERS = {
    "designer-profile": compose_designer_profile_result,
    "project-narrative": compose_project_narrative_result,
}


def compose_result(test_key: str, content: dict, answers: dict[str, str], session_id: str) -> dict:
    composer = RESULT_COMPOSERS.get(test_key)
    if composer is None:
        raise ContentNotFoundError(f"Нет result composer для test_key: {test_key!r}")
    return composer(content, answers, session_id)


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

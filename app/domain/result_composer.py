from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class TextFragment:
    id: str
    text: str


def deterministic_pick(fragments: list[TextFragment], seed: str, slot: str) -> TextFragment:
    """Выбирает вариативную формулировку воспроизводимо.

    Один и тот же session/scoring/content version даст тот же текст. Это позволяет
    тестировать результат и позже точно восстановить, что видел дизайнер.
    """
    if not fragments:
        raise ValueError("Нельзя выбрать фрагмент из пустого списка")
    digest = hashlib.sha256(f"{seed}:{slot}".encode("utf-8")).digest()
    index = int.from_bytes(digest[:8], "big") % len(fragments)
    return fragments[index]


def clamp_percent(value: float) -> int:
    return max(0, min(100, round(value)))


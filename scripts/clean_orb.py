"""Чистка анимированного шара из шапки.

Ролик снят на чёрном фоне и выбит по яркости, поэтому в кадрах остались серые
разводы и дымка: на светлом фоне приложения они читались как грязь, а сам шар —
как тусклый. Скрипт разводит цветное и бесцветное: цвет становится насыщеннее,
а всё, что почти обесцвечено, уходит в белый и перестаёт пачкать картинку.

Исходник (`docs/logo-orb-raw.webp`) остаётся нетронутым — правка обратима и
повторяема с другими числами, а не разовым волшебством.

    python scripts/clean_orb.py            # перезаписать webapp/assets/logo-orb.webp
    python scripts/clean_orb.py --preview   # лист сравнения в preview_orb.png
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageSequence

BASE_DIR = Path(__file__).resolve().parents[1]
SOURCE = BASE_DIR / "docs" / "logo-orb-raw.webp"
TARGET = BASE_DIR / "webapp" / "assets" / "logo-orb.webp"

# Яркость: степень меньше единицы раскатывает средние тона в свет — грязь
# бледнеет, а насыщенные места остаются собой.
V_GAMMA = 0.35
# Цвет: разводы должны быть цветными, а не сизыми.
S_GAIN = 1.55
# До какой насыщенности пиксель считается бесцветным и добеливается полностью.
WHITE_UPTO = 0.45
# Мягкость перехода к белому: больше единицы — переход плавнее у границы.
WHITE_POWER = 1.3
# 78 даёт файл размером с исходный; на сорока экранных пикселях разницы с 90 нет.
QUALITY = 78


def _to_hsv(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    red, green, blue = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    high, low = rgb.max(-1), rgb.min(-1)
    span = high - low
    hue = np.zeros_like(high)
    coloured = span > 1e-6
    index = coloured & (high == red)
    hue[index] = ((green - blue)[index] / span[index]) % 6
    index = coloured & (high == green)
    hue[index] = ((blue - red)[index] / span[index]) + 2
    index = coloured & (high == blue)
    hue[index] = ((red - green)[index] / span[index]) + 4
    return hue / 6, np.where(high > 1e-6, span / np.maximum(high, 1e-6), 0), high


def _to_rgb(hue: np.ndarray, sat: np.ndarray, val: np.ndarray) -> np.ndarray:
    sector = np.floor(hue * 6) % 6
    frac = hue * 6 - np.floor(hue * 6)
    p, q, t = val * (1 - sat), val * (1 - frac * sat), val * (1 - (1 - frac) * sat)
    out = np.zeros(hue.shape + (3,), np.float32)
    for number, trio in enumerate([(val, t, p), (q, val, p), (p, val, t),
                                   (p, q, val), (t, p, val), (val, p, q)]):
        mask = sector == number
        out[mask] = np.stack(trio, -1)[mask]
    return out


def clean_frame(frame: np.ndarray) -> np.ndarray:
    """Альфа не трогается: маска сферы и мягкий край уже такие, какие нужны."""
    rgb = frame[..., :3].astype(np.float32) / 255
    alpha = frame[..., 3:4]
    hue, sat, val = _to_hsv(rgb)
    val = np.clip(val ** V_GAMMA, 0, 1)
    sat = np.clip(sat * S_GAIN, 0, 1)
    out = _to_rgb(hue, sat, val)
    whiteness = (np.clip(1 - sat / WHITE_UPTO, 0, 1) ** WHITE_POWER)[..., None]
    out = out + (1 - out) * whiteness
    return np.concatenate([np.clip(out * 255, 0, 255), alpha], -1).astype(np.uint8)


def main() -> int:
    if not SOURCE.exists():
        print(f"Нет исходника: {SOURCE}")
        return 2

    animation = Image.open(SOURCE)
    frames, durations = [], []
    for frame in ImageSequence.Iterator(animation):
        frames.append(np.asarray(frame.convert("RGBA")))
        durations.append(frame.info.get("duration", animation.info.get("duration", 83)))
    cleaned = [Image.fromarray(clean_frame(frame)) for frame in frames]

    if "--preview" in sys.argv:
        picks = [0, 22, 44, 58]
        sheet = Image.new("RGBA", (300 * len(picks), 600), (248, 249, 251, 255))
        for column, index in enumerate(picks):
            sheet.alpha_composite(
                Image.fromarray(frames[index]).resize((300, 300), Image.LANCZOS), (column * 300, 0))
            sheet.alpha_composite(
                cleaned[index].resize((300, 300), Image.LANCZOS), (column * 300, 300))
        sheet.convert("RGB").save(BASE_DIR / "preview_orb.png")
        print("сверху исходник, снизу очищенный: preview_orb.png")
        return 0

    cleaned[0].save(TARGET, save_all=True, append_images=cleaned[1:], duration=durations,
                    loop=0, quality=QUALITY, method=6, minimize_size=True)
    print(f"{TARGET.name}: {len(cleaned)} кадров, {TARGET.stat().st_size} байт")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Собирает PDF деки webapp/presentation.html, который правится в Acrobat.

Golos Text с Google Fonts — вариативный шрифт, и Chromium кладёт такие в PDF
как Type3: Acrobat видит не текст, а набор картинок-букв. Поэтому для печати
шрифт подменяется статическими TTF из scripts/deck-fonts (сделаны из
GolosText[wght].ttf через fontTools instancer на 400/500/600).

    python scripts/deck_pdf.py [выходной.pdf]
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DECK = ROOT / "webapp" / "presentation.html"
FONTS = Path(__file__).resolve().parent / "deck-fonts"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
DEFAULT_OUT = Path.home() / "Downloads" / "IND_Interior_Bot_presentation.pdf"


def build_print_html() -> str:
    src = DECK.read_text(encoding="utf-8")
    faces = "".join(
        f"@font-face{{font-family:'Golos Text';font-weight:{w};"
        f"src:url('{(FONTS / f'GolosText-{w}.ttf').as_uri()}') format('truetype');}}\n"
        for w in (400, 500, 600)
    )
    anchor = '<meta charset="utf-8">'
    assert anchor in src, "в деке поменялась шапка — поправь якорь"
    src = src.replace("family=Golos+Text:wght@400;500;600&", "")
    base = f'<base href="{DECK.parent.as_uri()}/">'
    return src.replace(anchor, f"{anchor}\n{base}\n<style>{faces}</style>", 1)


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "deck-print.html"
        page.write_text(build_print_html(), encoding="utf-8")
        subprocess.run(
            [str(EDGE), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
             "--virtual-time-budget=10000", f"--print-to-pdf={out}", str(page)],
            check=True, capture_output=True,
        )
    print(out)


if __name__ == "__main__":
    main()

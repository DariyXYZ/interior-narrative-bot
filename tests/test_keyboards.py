from app.bot.keyboards import app_keyboard


def _webapp_url(markup) -> str:
    return markup.keyboard[0][0].web_app.url


def test_app_keyboard_plain_url_unchanged_without_screen() -> None:
    markup = app_keyboard("https://example.com/app/")
    assert _webapp_url(markup) == "https://example.com/app/"


def test_app_keyboard_appends_screen_param() -> None:
    markup = app_keyboard("https://example.com/app/", "results")
    assert _webapp_url(markup) == "https://example.com/app/?screen=results"


def test_app_keyboard_merges_screen_with_existing_query_string() -> None:
    # Регрессия: WEBAPP_URL с версией (?v=2) раньше ломался в "?v=2?screen=results".
    markup = app_keyboard("https://example.com/app/?v=2", "results")
    url = _webapp_url(markup)
    assert url.count("?") == 1
    assert "v=2" in url
    assert "screen=results" in url


def test_app_keyboard_carries_session_token() -> None:
    markup = app_keyboard("https://example.com/app/?v=3", None, "42.999.deadbeef")
    url = _webapp_url(markup)
    assert url.count("?") == 1
    assert "v=3" in url
    assert "t=42.999.deadbeef" in url


def test_app_keyboard_combines_screen_and_token() -> None:
    url = _webapp_url(app_keyboard("https://example.com/app/", "results", "42.999.deadbeef"))
    assert "screen=results" in url
    assert "t=42.999.deadbeef" in url


def test_app_keyboard_skips_empty_token() -> None:
    # Токен не выдался (нет БД) — кнопка всё равно должна остаться рабочей.
    assert _webapp_url(app_keyboard("https://example.com/app/", None, None)) == "https://example.com/app/"

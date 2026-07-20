from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl


class TelegramAuthError(ValueError):
    pass


@dataclass(frozen=True)
class TelegramIdentity:
    user: dict
    auth_date: int
    query_id: str | None


def validate_init_data(init_data: str, bot_token: str, max_age_seconds: int) -> TelegramIdentity:
    if not init_data:
        raise TelegramAuthError("Telegram initData отсутствует")

    values = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = values.pop("hash", "")
    if not received_hash:
        raise TelegramAuthError("Telegram initData не содержит hash")

    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise TelegramAuthError("Неверная подпись Telegram initData")

    try:
        auth_date = int(values.get("auth_date", "0"))
    except ValueError as exc:
        raise TelegramAuthError("Некорректная дата Telegram initData") from exc
    if auth_date <= 0 or time.time() - auth_date > max_age_seconds:
        raise TelegramAuthError("Telegram initData устарел")

    try:
        user = json.loads(values["user"])
        int(user["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TelegramAuthError("Telegram initData не содержит корректного пользователя") from exc

    return TelegramIdentity(user=user, auth_date=auth_date, query_id=values.get("query_id"))


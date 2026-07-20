import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app.api.telegram_auth import TelegramAuthError, validate_init_data


def _signed_init_data(token: str, auth_offset: int = 0) -> str:
    values = {
        "auth_date": str(int(time.time()) + auth_offset),
        "query_id": "test-query",
        "user": json.dumps({"id": 42, "first_name": "D", "username": "designer"}, separators=(",", ":")),
    }
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


def test_valid_init_data() -> None:
    identity = validate_init_data(_signed_init_data("token"), "token", 60)
    assert identity.user["id"] == 42
    assert identity.user["username"] == "designer"


def test_expired_init_data() -> None:
    with pytest.raises(TelegramAuthError):
        validate_init_data(_signed_init_data("token", auth_offset=-120), "token", 60)


def test_future_init_data() -> None:
    with pytest.raises(TelegramAuthError):
        validate_init_data(_signed_init_data("token", auth_offset=86400), "token", 60)


def test_tampered_hash() -> None:
    with pytest.raises(TelegramAuthError):
        validate_init_data(_signed_init_data("token")[:-4] + "0000", "token", 60)


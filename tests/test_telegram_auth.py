import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app.api.telegram_auth import (
    TelegramAuthError,
    issue_session_token,
    validate_init_data,
    verify_session_token,
)


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


def test_session_token_roundtrip() -> None:
    token = issue_session_token(42, "token", ttl_seconds=3600)
    assert verify_session_token(token, "token") == 42


def test_session_token_rejects_wrong_secret() -> None:
    token = issue_session_token(42, "token", ttl_seconds=3600)
    assert verify_session_token(token, "other-token") is None


def test_session_token_rejects_tampered_payload() -> None:
    token = issue_session_token(42, "token", ttl_seconds=3600)
    uid, exp, sig = token.split(".")
    tampered = f"999.{exp}.{sig}"
    assert verify_session_token(tampered, "token") is None


def test_session_token_rejects_expired() -> None:
    token = issue_session_token(42, "token", ttl_seconds=3600, now=1_000_000)
    assert verify_session_token(token, "token", now=1_000_000 + 3601) is None


def test_session_token_rejects_garbage() -> None:
    assert verify_session_token("not-a-token", "token") is None
    assert verify_session_token("", "token") is None


"""Unit tests for Telegram Mini App initData verification."""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from web import telegram_auth

BOT_TOKEN = "12345:TEST-TOKEN"


def _signed_init_data(
    token: str = BOT_TOKEN,
    user_id: int = 987654321,
    auth_date: int | None = None,
    tamper: bool = False,
) -> str:
    """Build an initData query string signed exactly as Telegram does."""
    fields = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAF-test",
        "user": json.dumps({"id": user_id, "first_name": "Test"}),
    }
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if tamper:
        fields["user"] = json.dumps({"id": 1, "first_name": "Mallory"})
    return urlencode(fields)


class TestVerify:
    def test_valid_signature_accepted(self):
        fields = telegram_auth.verify_init_data(_signed_init_data(), BOT_TOKEN)
        assert fields is not None
        assert telegram_auth.user_id_from(fields) == "987654321"

    def test_tampered_payload_rejected(self):
        # Fields changed after signing — the signature no longer matches.
        assert telegram_auth.verify_init_data(_signed_init_data(tamper=True), BOT_TOKEN) is None

    def test_wrong_token_rejected(self):
        data = _signed_init_data(token="999:OTHER-TOKEN")
        assert telegram_auth.verify_init_data(data, BOT_TOKEN) is None

    def test_stale_auth_date_rejected(self):
        old = int(time.time()) - telegram_auth.MAX_AGE_SECONDS - 60
        data = _signed_init_data(auth_date=old)
        assert telegram_auth.verify_init_data(data, BOT_TOKEN) is None

    def test_missing_hash_rejected(self):
        assert telegram_auth.verify_init_data("auth_date=1&user=x", BOT_TOKEN) is None

    def test_empty_inputs_rejected(self):
        assert telegram_auth.verify_init_data("", BOT_TOKEN) is None
        assert telegram_auth.verify_init_data(_signed_init_data(), "") is None


class TestUserId:
    def test_missing_user_field(self):
        assert telegram_auth.user_id_from({}) is None

    def test_malformed_user_json(self):
        assert telegram_auth.user_id_from({"user": "not-json"}) is None

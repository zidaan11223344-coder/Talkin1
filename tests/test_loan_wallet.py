from io import BytesIO
from unittest.mock import patch

import pytest

import bot as bot_module


@pytest.fixture
def isolated_points(monkeypatch):
    accounts = {}
    history = []
    monkeypatch.setattr(bot_module, "_POINTS_CACHE", accounts)
    monkeypatch.setattr(bot_module, "_POINTS_TRANSFER_CACHE", history)
    monkeypatch.setattr(bot_module, "_STATE_DB_ENABLED", False)
    monkeypatch.setattr(bot_module, "_save_local_json", lambda *args, **kwargs: None)
    return accounts, history


def account(username):
    resolved = bot_module._resolve_points_account(bot_module._points_data(), username)
    return resolved[1] if resolved else {}


def test_loan_requires_balance_below_100b_and_blocks_second_open_loan(isolated_points):
    bot_module._POINTS_CACHE["alice"] = {"username": "Alice", "points": 99_000_000_000}

    issued = bot_module._request_points_loan("Alice")
    assert issued["ok"] is True
    assert issued["balance"] == 199_000_000_000
    assert account("Alice")["loan_debt"] == 100_000_000_000

    blocked = bot_module._request_points_loan("Alice")
    assert blocked["error"] == "outstanding_loan"
    assert blocked["loan_debt"] == 100_000_000_000


def test_loan_repayment_withholds_20_percent_once_and_stops_when_paid(isolated_points):
    bot_module._POINTS_CACHE["alice"] = {"username": "Alice", "points": 99_000_000_000}
    bot_module._request_points_loan("Alice")

    first = bot_module._apply_points_delta_once(
        "Alice", 50_000_000_000, "reward-1", "game prize", repay_loan=True
    )
    retry = bot_module._apply_points_delta_once(
        "Alice", 50_000_000_000, "reward-1", "game prize", repay_loan=True
    )
    assert first["loan_repayment"] == 10_000_000_000
    assert first["loan_debt"] == 90_000_000_000
    assert first["balance"] == 239_000_000_000
    assert retry["already_applied"] is True
    assert retry["balance"] == first["balance"]
    assert account("Alice")["loan_debt"] == 90_000_000_000

    final = bot_module._apply_points_delta_once(
        "Alice", 500_000_000_000, "reward-2", "game prize", repay_loan=True
    )
    assert final["loan_repayment"] == 90_000_000_000
    assert final["loan_debt"] == 0
    assert account("Alice")["loan_repay_carry"] == 0


def test_loan_is_denied_when_balance_is_100b_or_more(isolated_points):
    bot_module._POINTS_CACHE["alice"] = {"username": "Alice", "points": 100_000_000_000}
    result = bot_module._request_points_loan("Alice")
    assert result["error"] == "balance_too_high"
    assert bot_module._points_balance(account("Alice")) == 100_000_000_000


def test_wallet_purchase_is_persisted_and_profit_sale_reduces_loan_only_from_profit(isolated_points):
    bot_module._POINTS_CACHE["alice"] = {
        "username": "Alice", "points": 1_000, "loan_debt": 100, "loan_repay_carry": 0,
    }
    purchased = bot_module._create_wallet_position("Alice", 1, 500, room="Hall", now=100)
    assert purchased["ok"] is True
    assert purchased["balance"] == 500
    position_id = purchased["position"]["id"]
    assert purchased["position"]["due_at"] == 3_700
    assert len(account("Alice")["wallet_positions"]) == 1
    assert bot_module._wallet_due_positions(now=3_699) == []
    assert bot_module._wallet_due_positions(now=3_700) == [("Alice", position_id)]

    with patch.object(bot_module.secrets, "randbelow", return_value=1):
        sold = bot_module._settle_wallet_position("Alice", position_id, now=3_700)
    assert sold["ok"] is True
    assert sold["outcome"] == "profit"
    assert sold["principal"] == 500
    assert sold["payout"] == 525
    assert sold["loan_repayment"] == 5  # 20% of the 25-point profit, not the principal
    assert sold["loan_debt"] == 95
    assert sold["balance"] == 1_020
    assert account("Alice")["wallet_positions"] == []
    assert account("Alice")["wallet_history"][-1]["outcome"] == "profit"

    retried = bot_module._settle_wallet_position("Alice", position_id, now=3_701)
    assert retried["already_applied"] is True
    assert bot_module._points_balance(account("Alice")) == 1_020


def test_wallet_loss_returns_95_percent_and_does_not_repay_loan(isolated_points):
    bot_module._POINTS_CACHE["alice"] = {
        "username": "Alice", "points": 1_000, "loan_debt": 100, "loan_repay_carry": 0,
    }
    purchased = bot_module._create_wallet_position("Alice", 2, 500, room="Hall", now=10)
    position_id = purchased["position"]["id"]
    with patch.object(bot_module.secrets, "randbelow", return_value=0):
        sold = bot_module._settle_wallet_position("Alice", position_id, now=3_610)
    assert sold["outcome"] == "loss"
    assert sold["payout"] == 475
    assert sold["loan_repayment"] == 0
    assert sold["loan_debt"] == 100
    assert sold["balance"] == 975


def test_wallet_parser_and_twenty_item_catalog_pages():
    assert bot_module._parse_wallet_purchase("شراء ذهب 30b") == (1, 30_000_000_000)
    assert bot_module._parse_wallet_purchase("شراء 20 1m") == (20, 1_000_000)
    assert len(bot_module.WALLET_ASSETS) == 20
    assert bot_module.WALLET_PAGE_SIZE == 10
    assert bot_module._looks_like_bot_command("سلفني")
    assert bot_module._looks_like_bot_command("محفظة")
    assert bot_module._looks_like_bot_command("شراء نفط 1b")


def test_wallet_settlement_worker_runs_until_stop_event():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    calls = []

    class StopEvent:
        stopped = False

        def is_set(self):
            return self.stopped

        def wait(self, _seconds):
            self.stopped = True

    bot.stop_event = StopEvent()
    bot.log = lambda *_args: None
    bot._process_wallet_investments = lambda: calls.append("settle")
    bot._wallet_settlement_worker()

    assert calls == ["settle"]


def test_profile_decoder_accepts_string_keys_and_plain_profile_fields():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    numeric = bot._decode_user_item_candidate({"1": "Player", "3": "https://cdn.example/a.jpg"})
    plain = bot._decode_user_item_candidate({"username": "Alice", "avatar_url": "https://cdn.example/b.png"})
    assert numeric[0]["username"] == "Player"
    assert numeric[0]["photo"] == "https://cdn.example/a.jpg"
    assert plain[0]["username"] == "Alice"
    assert plain[0]["photo"] == "https://cdn.example/b.png"


def test_profile_photo_cache_reads_string_key_users_payload():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot.user_photos = {}
    bot._profile_status_lock = __import__("threading").RLock()
    bot._cache_user_photos_from_result({
        "users": [{"username": "Alice", "photo_url": "https://cdn.example/alice.jpg"}]
    })
    assert bot.user_photos["alice"] == "https://cdn.example/alice.jpg"


def test_shared_profile_downloader_decodes_and_caches_image_bytes():
    if not bot_module.PIL_AVAILABLE:
        pytest.skip("Pillow not available")
    from PIL import Image

    output = BytesIO()
    Image.new("RGB", (20, 12), (220, 30, 40)).save(output, format="PNG")
    response = type("Response", (), {"status_code": 200, "content": output.getvalue()})()
    bot_module._PROFILE_PHOTO_CACHE.clear()
    with patch.object(bot_module.requests, "get", return_value=response) as request:
        first = bot_module._download_profile_photo("https://cdn.example/avatar.png")
        second = bot_module._download_profile_photo("https://cdn.example/avatar.png")
    assert first is not None and second is not None
    assert first.size == (20, 12)
    assert first.getpixel((0, 0)) == (220, 30, 40)
    request.assert_called_once()

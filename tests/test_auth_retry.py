from unittest.mock import patch

import bot as bot_module


class FakeResponse:
    content = b"auth-result"

    def raise_for_status(self):
        return None


class FakeHttp:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def post(self, *_args, **_kwargs):
        self.calls += 1
        return self.responses.pop(0)


def _auth_result(result, message=""):
    return {
        "result": result,
        "message": message,
        "user_id": "123",
        "server": "5335",
        "id": "captcha-session",
        "photo_version": "0",
    }


def test_auth_retries_only_the_servers_generic_temporary_rejection():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot.http = FakeHttp([FakeResponse(), FakeResponse()])
    bot.log = lambda *_args: None
    decoded = [_auth_result("error", "Unknown error occurred. Try again!"), _auth_result("ok")]
    with patch.object(bot_module, "decode_auth_result", side_effect=decoded), patch.object(
        bot_module.time, "sleep", lambda _seconds: None
    ):
        result = bot.authenticate()
    assert result["result"] == "ok"
    assert bot.http.calls == 2


def test_auth_does_not_retry_permanent_rejection():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot.http = FakeHttp([FakeResponse(), FakeResponse()])
    bot.log = lambda *_args: None
    with patch.object(
        bot_module, "decode_auth_result",
        return_value=_auth_result("error", "Invalid username or password"),
    ), patch.object(bot_module.time, "sleep", lambda _seconds: None):
        try:
            bot.authenticate()
        except RuntimeError as exc:
            assert "Invalid username or password" in str(exc)
        else:
            raise AssertionError("permanent authentication rejection must fail")
    assert bot.http.calls == 1

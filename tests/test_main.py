"""app.main の dispatch table を検証する。"""

from __future__ import annotations

import pytest

from app import main


def test_commands_cover_5() -> None:
    assert set(main.COMMANDS) == {"seed", "sync", "seed-raw", "build-features", "export"}


def test_dispatch_calls_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []
    monkeypatch.setitem(main.COMMANDS, "seed", lambda: called.append("seed"))
    assert main.main(["prog", "seed"]) == 0
    assert called == ["seed"]


def test_no_args_returns_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main.main(["prog"]) == 2
    assert "usage" in capsys.readouterr().err


def test_unknown_command_returns_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main.main(["prog", "bogus"]) == 2
    assert "unknown command" in capsys.readouterr().err

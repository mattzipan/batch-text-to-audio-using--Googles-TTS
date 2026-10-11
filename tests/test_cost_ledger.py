"""Tests for app.cost_ledger: XDG roundtrip, month buckets, atomic write."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from app import cost_ledger


@pytest.fixture()
def xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    return tmp_path


def test_roundtrip_under_tmp_xdg(xdg: Path) -> None:
    cost_ledger.record("translate", 0.1234567)
    path = xdg / "WordTape" / "costs.json"
    assert path.is_file()
    data = cost_ledger.load()
    assert data["pricing_version"] == "2026-09-22+intro"
    month = datetime.now().strftime("%Y-%m")
    bucket = data["months"][month]
    assert bucket["translate_usd"] == 0.123457  # rounded to 6 decimals
    assert bucket["tts_usd"] == 0.0
    assert bucket["calls"] == 1
    assert set(bucket) == {"translate_usd", "tts_usd", "calls", "updated_at"}
    # schema wrapper is exactly as specced
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert set(raw) == {"months", "pricing_version"}


def test_record_accumulates_and_counts_calls(xdg: Path) -> None:
    cost_ledger.record("tts", 0.000001)
    cost_ledger.record("tts", 0.000002)
    cost_ledger.record("translate", 0.25)
    month = datetime.now().strftime("%Y-%m")
    bucket = cost_ledger.load()["months"][month]
    assert bucket["tts_usd"] == 0.000003  # accumulated sum rounded to 6 dp
    assert bucket["translate_usd"] == 0.25
    assert bucket["calls"] == 3


def test_six_decimal_rounding(xdg: Path) -> None:
    cost_ledger.record("translate", 1 / 3)
    month = datetime.now().strftime("%Y-%m")
    assert cost_ledger.load()["months"][month]["translate_usd"] == 0.333333


def test_month_bucket_rollover(xdg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeDateTime:
        current = datetime(2026, 10, 15, 12, 0, 0)

        @classmethod
        def now(cls):
            return cls.current

    monkeypatch.setattr(cost_ledger, "datetime", FakeDateTime)
    cost_ledger.record("tts", 0.5)
    FakeDateTime.current = datetime(2026, 11, 1, 0, 0, 0)
    cost_ledger.record("translate", 0.25)
    data = cost_ledger.load()
    assert set(data["months"]) == {"2026-10", "2026-11"}
    oct_bucket = data["months"]["2026-10"]
    assert oct_bucket["tts_usd"] == 0.5
    assert oct_bucket["translate_usd"] == 0.0
    assert oct_bucket["calls"] == 1
    assert oct_bucket["updated_at"] == "2026-10-15T12:00:00"
    nov_bucket = data["months"]["2026-11"]
    assert nov_bucket["translate_usd"] == 0.25
    assert nov_bucket["calls"] == 1


def test_atomic_write_tmp_then_replace(xdg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_replace = os.replace
    seen: dict = {}

    def spy(src, dst):
        src_path = Path(src)
        seen["tmp_exists"] = src_path.exists()
        seen["tmp_name"] = src_path.name
        seen["dest"] = Path(dst)
        seen["content"] = json.loads(src_path.read_text(encoding="utf-8"))
        return real_replace(src, dst)

    monkeypatch.setattr(cost_ledger.os, "replace", spy)
    cost_ledger.record("translate", 0.25)
    assert seen["tmp_exists"] is True
    assert seen["tmp_name"] == "costs.json.tmp"
    assert seen["dest"] == cost_ledger.ledger_path()
    assert seen["content"]["months"]  # valid JSON hit the tmp before replace
    leftover = cost_ledger.ledger_path().parent / "costs.json.tmp"
    assert not leftover.exists()


def test_record_never_raises_on_write_failure(xdg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(cost_ledger, "_atomic_write", boom)
    cost_ledger.record("tts", 0.5)  # must not raise


def test_record_never_raises_on_unreadable_ledger(xdg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bad = xdg / "WordTape" / "costs.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("{corrupt", encoding="utf-8")
    cost_ledger.record("tts", 0.5)  # corrupt load is tolerated, not raised
    bucket = cost_ledger.load()["months"][datetime.now().strftime("%Y-%m")]
    assert bucket["tts_usd"] == 0.5


def test_unknown_kind_is_a_silent_noop(xdg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(cost_ledger, "_atomic_write", lambda *a, **k: calls.append(a))
    cost_ledger.record("bogus", 1.0)  # must not raise
    assert calls == []
    assert cost_ledger.load()["months"] == {}


def test_summary_pure_payload_from_ledger_dict() -> None:
    data = {
        "months": {
            "2026-08": {"translate_usd": 0.10, "tts_usd": 0.20, "calls": 4, "updated_at": "x"},
            "2026-10": {"translate_usd": 0.05, "tts_usd": 0.37, "calls": 9, "updated_at": "y"},
        },
        "pricing_version": "2026-09-22+intro",
    }
    payload = cost_ledger.summary(data)
    assert payload["current_month"] == datetime.now().strftime("%Y-%m")
    assert payload["pricing_version"] == "2026-09-22+intro"
    assert "AI Studio Billing" in payload["note"]
    assert payload["current"] == {
        "translate_usd": 0.05,
        "tts_usd": 0.37,
        "total_usd": 0.42,
        "calls": 9,
    }
    assert [row["month"] for row in payload["history"]] == ["2026-10", "2026-08"]
    assert payload["history"][0]["total_usd"] == 0.42
    assert payload["history"][1]["total_usd"] == 0.30


def test_summary_empty_ledger(xdg: Path) -> None:
    payload = cost_ledger.summary()
    month = datetime.now().strftime("%Y-%m")
    assert payload["history"] == []
    assert payload["current"] == {
        "translate_usd": 0.0,
        "tts_usd": 0.0,
        "total_usd": 0.0,
        "calls": 0,
    }
    assert payload["current_month"] == month
    assert "Estimates" in payload["note"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

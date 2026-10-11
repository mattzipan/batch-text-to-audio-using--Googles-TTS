"""Mocked tests for app.translate (never touches the network)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app import config
from app.project import Row
from app import translate as translate_mod
from app.translate import translate_rows


def make_rows(n: int, prefix: str = "r") -> list[Row]:
    return [
        Row(id=f"{prefix}{i:02d}", position=i + 1, source=f"word{i}", variants=[])
        for i in range(n)
    ]


def make_response(payload: str) -> MagicMock:
    resp = MagicMock()
    resp.text = payload
    return resp


def make_entries(n: int, offset: int = 0) -> list[dict]:
    return [
        {
            "source": f"word{offset + i}",
            "translation": f"trans{offset + i}",
            "formal": None,
            "informal": None,
        }
        for i in range(n)
    ]


def get_contents(mock_client: MagicMock, call_index: int = 0) -> str:
    call = mock_client.models.generate_content.call_args_list[call_index]
    if call.kwargs.get("contents") is not None:
        return call.kwargs["contents"]
    for arg in call.args:
        if isinstance(arg, str):
            return arg
    raise AssertionError("contents not found in generate_content call")


def test_batching_boundary_26_rows_two_calls() -> None:
    rows = make_rows(26)
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        make_response(json.dumps(make_entries(25, 0))),
        make_response(json.dumps(make_entries(1, 25))),
    ]
    result = translate_rows(rows, "de", "id", True, client=mock_client)
    assert mock_client.models.generate_content.call_count == 2
    assert len(result) == 26
    assert result["r00"]["translation"] == "trans0"
    assert result["r25"]["translation"] == "trans25"


def test_json_parse_including_fenced_json() -> None:
    rows = make_rows(2)
    payload = (
        "```json\n"
        + json.dumps(
            [
                {"source": "word0", "translation": "alpha", "formal": "A", "informal": "a"},
                {"source": "word1", "translation": "beta", "formal": None, "informal": None},
            ]
        )
        + "\n```"
    )
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = make_response(payload)
    result = translate_rows(rows, "de", "id", True, client=mock_client)
    assert result["r00"] == {"translation": "alpha", "formal": "A", "informal": "a"}
    assert result["r01"] == {"translation": "beta", "formal": None, "informal": None}


def test_variants_off_prompt_omits_formal_informal() -> None:
    rows = make_rows(1)
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = make_response(
        json.dumps([{"source": "word0", "translation": "x"}])
    )
    result = translate_rows(rows, "de", "id", False, client=mock_client)
    contents = get_contents(mock_client).lower()
    assert "formal" not in contents
    assert "informal" not in contents
    assert result["r00"] == {"translation": "x", "formal": None, "informal": None}

    # Variants-on prompt must mention both registers.
    mock_client2 = MagicMock()
    mock_client2.models.generate_content.return_value = make_response(
        json.dumps(
            [{"source": "word0", "translation": "x", "formal": "F", "informal": "I"}]
        )
    )
    result2 = translate_rows(rows, "de", "id", True, client=mock_client2)
    contents_on = get_contents(mock_client2).lower()
    assert "formal" in contents_on
    assert "informal" in contents_on
    assert result2["r00"] == {"translation": "x", "formal": "F", "informal": "I"}


def test_parse_failure_retry_then_error() -> None:
    rows = make_rows(1)
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        make_response("this is not json"),
        make_response("still not json {{{"),
    ]
    with pytest.raises(RuntimeError, match="batch"):
        translate_rows(rows, "de", "id", True, client=mock_client)
    assert mock_client.models.generate_content.call_count == 2
    retry_contents = get_contents(mock_client, 1)
    assert "ONLY valid JSON" in retry_contents


def test_429_backoff_then_success() -> None:
    rows = make_rows(1)
    transient = RuntimeError("429 RESOURCE_EXHAUSTED: quota hit")
    transient.code = 429  # type: ignore[attr-defined]
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        transient,
        make_response(json.dumps(make_entries(1, 0))),
    ]
    with patch.object(translate_mod.time, "sleep") as mock_sleep:
        result = translate_rows(rows, "de", "id", True, client=mock_client)
    assert result["r00"]["translation"] == "trans0"
    assert mock_client.models.generate_content.call_count == 2
    assert mock_sleep.call_count == 1
    assert mock_sleep.call_args_list[0][0][0] == 2.0


def test_auth_error_aborts_immediately() -> None:
    rows = make_rows(2)
    auth_err = RuntimeError("API key not valid. Please pass a valid API key.")
    auth_err.code = 403  # type: ignore[attr-defined]
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = auth_err
    with patch.object(translate_mod.time, "sleep") as mock_sleep:
        with pytest.raises(RuntimeError, match="[Aa]uth|API key"):
            translate_rows(rows, "de", "id", True, client=mock_client)
    assert mock_client.models.generate_content.call_count == 1
    mock_sleep.assert_not_called()


def test_cancel_stops_before_second_chunk() -> None:
    rows = make_rows(26)
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = make_response(
        json.dumps(make_entries(25, 0))
    )
    cancel = MagicMock(side_effect=[False, True])
    with pytest.raises(RuntimeError, match="cancelled"):
        translate_rows(rows, "de", "id", True, client=mock_client, cancel=cancel)
    assert mock_client.models.generate_content.call_count == 1


def test_row_id_mapping_by_position() -> None:
    rows = [
        Row(id="id-c", position=1, source="Apfel", variants=[]),
        Row(id="id-a", position=2, source="Birne", variants=[]),
        Row(id="id-b", position=3, source="Kirsche", variants=[]),
    ]
    # Deliberately wrong/mismatched source echoes: mapping must be positional.
    payload = json.dumps(
        [
            {"source": "WRONG-0", "translation": "T1", "formal": None, "informal": None},
            {"source": "WRONG-1", "translation": None, "formal": "F2", "informal": None},
            {"source": "WRONG-2", "translation": "T3"},
        ]
    )
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = make_response(payload)
    result = translate_rows(rows, "de", "id", True, client=mock_client)
    assert result["id-c"] == {"translation": "T1", "formal": None, "informal": None}
    # Null translation coerces to "".
    assert result["id-a"] == {"translation": "", "formal": "F2", "informal": None}
    # Missing formal/informal keys become None.
    assert result["id-b"] == {"translation": "T3", "formal": None, "informal": None}


def test_uses_configured_model_and_json_mime() -> None:
    rows = make_rows(1)
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = make_response(
        json.dumps(make_entries(1, 0))
    )
    translate_rows(rows, "de", "id", True, client=mock_client)
    call = mock_client.models.generate_content.call_args_list[0]
    assert call.kwargs["model"] == config.TRANSLATION_MODEL
    assert call.kwargs["config"].response_mime_type == "application/json"


def test_progress_called_after_each_chunk() -> None:
    rows = make_rows(26)
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        make_response(json.dumps(make_entries(25, 0))),
        make_response(json.dumps(make_entries(1, 25))),
    ]
    seen: list[tuple[int, int]] = []
    translate_rows(
        rows, "de", "id", True, client=mock_client, progress=lambda d, t: seen.append((d, t))
    )
    assert seen == [(25, 26), (26, 26)]


def make_usage(prompt: int = 1000, candidates: int = 400):
    from types import SimpleNamespace

    return SimpleNamespace(prompt_token_count=prompt, candidates_token_count=candidates)


def make_response_with_usage(payload: str, usage) -> MagicMock:
    resp = make_response(payload)
    resp.usage_metadata = usage
    return resp


def test_collect_costs_appends_estimate_per_successful_call() -> None:
    rows = make_rows(2)
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = make_response_with_usage(
        json.dumps(make_entries(2, 0)), make_usage(1000, 400)
    )
    costs: list[float] = []
    result = translate_rows(
        rows, "de", "id", True, client=mock_client, collect_costs=costs
    )
    assert result["r00"]["translation"] == "trans0"
    # F11 verify math: prompt×$0.30/1M + candidates×$2.50/1M
    assert len(costs) == 1
    assert costs[0] == pytest.approx(1000 / 1e6 * 0.30 + 400 / 1e6 * 2.50)


def test_collect_costs_counts_parse_retry_as_second_estimate() -> None:
    rows = make_rows(1)
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        make_response_with_usage("this is not json", make_usage(500, 100)),
        make_response_with_usage(json.dumps(make_entries(1, 0)), make_usage(520, 110)),
    ]
    costs: list[float] = []
    translate_rows(rows, "de", "id", True, client=mock_client, collect_costs=costs)
    assert len(costs) == 2
    assert costs[0] == pytest.approx(500 / 1e6 * 0.30 + 100 / 1e6 * 2.50)
    assert costs[1] == pytest.approx(520 / 1e6 * 0.30 + 110 / 1e6 * 2.50)


def test_collect_costs_skips_none_usage() -> None:
    rows = make_rows(1)
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = make_response_with_usage(
        json.dumps(make_entries(1, 0)), None
    )
    costs: list[float] = []
    translate_rows(rows, "de", "id", True, client=mock_client, collect_costs=costs)
    assert costs == []  # omitted, never $0.00 for unknown


def test_collect_costs_transient_retry_inside_call_counts_once() -> None:
    rows = make_rows(1)
    transient = RuntimeError("429 RESOURCE_EXHAUSTED: quota hit")
    transient.code = 429  # type: ignore[attr-defined]
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        transient,  # no response → no usage to cost
        make_response_with_usage(json.dumps(make_entries(1, 0)), make_usage(300, 90)),
    ]
    costs: list[float] = []
    with patch.object(translate_mod.time, "sleep"):
        translate_rows(rows, "de", "id", True, client=mock_client, collect_costs=costs)
    # one _call_with_retries return → one estimate (raw response kept)
    assert len(costs) == 1
    assert costs[0] == pytest.approx(300 / 1e6 * 0.30 + 90 / 1e6 * 2.50)


def test_collect_costs_batches_accumulate() -> None:
    rows = make_rows(26)
    usage = make_usage(1000, 400)
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        make_response_with_usage(json.dumps(make_entries(25, 0)), usage),
        make_response_with_usage(json.dumps(make_entries(1, 25)), usage),
    ]
    costs: list[float] = []
    translate_rows(rows, "de", "id", True, client=mock_client, collect_costs=costs)
    assert len(costs) == 2
    assert costs == pytest.approx([costs[0], costs[0]])

import json
import logging
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

from src.handlers import artist as handler
from src.services.musicbrainz import client as mb
from src.utils.telemetry import InvocationMetrics, activate, deactivate


def _records(caplog):
    return [json.loads(record.message) for record in caplog.records
            if record.message.startswith('{"event":"artist_pipeline_completed"')]


def test_success_emits_one_safe_record_and_preserves_response(caplog):
    caplog.set_level(logging.INFO)
    result = {"artist": {"name": "Secret Artist", "biography": "private bio"},
              "sources": {"theaudiodb": True, "musicbrainz": False}}
    handler._cold_start = True
    with patch.object(handler, "process_enriched_artist", return_value=result):
        response = handler.lambda_handler(
            {"pathParameters": {"artist_name": "Secret Artist"}},
            SimpleNamespace(aws_request_id="request-123"),
        )

    assert response == {"statusCode": 200, "headers": {
        "Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"artist": result["artist"],
                            "metadata": {"sources": result["sources"]}},
                           ensure_ascii=False)}
    records = _records(caplog)
    assert len(records) == 1
    record = records[0]
    assert record["outcome"] == "success"
    assert record["request_id"] == "request-123"
    assert record["cold_start"] is True
    assert record["metrics"]["lambda.cold_start"] is True
    assert record["metrics"]["response_bytes"] == len(response["body"].encode())
    assert all(value >= 0 for key, value in record["metrics"].items()
               if key.endswith("_ms"))
    assert "Secret Artist" not in caplog.text
    assert "private bio" not in caplog.text


def test_failure_still_emits_warm_record_without_payload(caplog):
    caplog.set_level(logging.INFO)
    secret = "api-key-never-log"
    with patch.object(handler, "process_enriched_artist", side_effect=RuntimeError(secret)):
        response = handler.lambda_handler(
            {"pathParameters": {"artist_name": "Name"}},
            SimpleNamespace(aws_request_id="request-456"),
        )
    assert response["statusCode"] == 500
    record = _records(caplog)[-1]
    assert record["outcome"] == "internal_error"
    assert record["cold_start"] is False
    assert secret not in caplog.text


def test_validation_failure_has_telemetry_and_no_request_id(caplog):
    caplog.set_level(logging.INFO)
    response = handler.lambda_handler({"pathParameters": {}}, None)
    assert response["statusCode"] == 400
    record = _records(caplog)[-1]
    assert record["request_id"] is None
    assert record["outcome"] == "validation_error"
    assert record["metrics"]["handler.validation_ms"] >= 0


def test_musicbrainz_attempt_retry_http_and_wait_metrics(monkeypatch):
    now = [10.0]
    metrics = InvocationMetrics(clock=lambda: now[0])
    token = activate(metrics)
    mb._last_request_started_at = 9.5
    response = Mock(status_code=200, headers={})
    response.raise_for_status.side_effect = [requests.Timeout("hidden"), None]
    response.json.return_value = {"artists": [{"id": "id", "name": "name"}]}
    monkeypatch.setattr(mb.requests, "get", Mock(return_value=response))
    monkeypatch.setattr(mb.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(mb.time, "sleep", lambda delay: now.__setitem__(0, now[0] + delay))
    try:
        mb.search_artist("name")
    finally:
        deactivate(token)
    values = metrics.snapshot()
    assert values["musicbrainz.attempts"] == 2
    assert values["musicbrainz.requests"] == 2
    assert values["musicbrainz.retries"] == 1
    assert values["musicbrainz.rate_limit_wait_ms"] == 500.0
    assert values["musicbrainz.retry_wait_ms"] == 1000.0
    assert values["musicbrainz.http_ms"] >= 0


def test_release_group_pages_are_counted(monkeypatch):
    pages = [{"release-groups": [{"id": "one"}], "release-group-count": 2},
             {"release-groups": [{"id": "two"}], "release-group-count": 2}]
    metrics = InvocationMetrics()
    token = activate(metrics)
    monkeypatch.setattr(mb, "_get_json", Mock(side_effect=pages))
    monkeypatch.setattr(mb, "RELEASE_GROUP_PAGE_SIZE", 1)
    try:
        result = mb.get_release_groups("mbid")
    finally:
        deactivate(token)
    assert result["pages-fetched"] == 2
    assert metrics.snapshot()["musicbrainz.pages"] == 2

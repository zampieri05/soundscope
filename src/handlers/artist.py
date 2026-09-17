"""AWS Lambda proxy handler for enriched artist processing."""

from dataclasses import asdict, is_dataclass
import json
import logging
from typing import Any

from src.pipeline.ingestion.errors import UsableArtistNotFoundError
from src.pipeline.processing import (
    EnrichedArtistProcessingResult,
    process_enriched_artist,
)
from src.services.musicbrainz.client import (
    ArtistNotFoundError as MusicBrainzArtistNotFoundError,
    MusicBrainzError,
)
from src.services.theaudiodb.client import (
    ArtistNotFoundError as TheAudioDBArtistNotFoundError,
    TheAudioDBError,
)
from src.utils.telemetry import InvocationMetrics, activate, deactivate


logger = logging.getLogger(__name__)
_cold_start = True

_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}
_NOT_FOUND_ERRORS = (
    TheAudioDBArtistNotFoundError,
    MusicBrainzArtistNotFoundError,
    UsableArtistNotFoundError,
)


def _response(status_code: int, body: Any) -> dict[str, Any]:
    """Build an API Gateway Lambda proxy response with a JSON body."""
    return {
        "statusCode": status_code,
        "headers": _HEADERS.copy(),
        "body": json.dumps(body, ensure_ascii=False, default=_json_default),
    }


def _json_default(value: Any) -> Any:
    """Convert domain dataclasses, including nested ones, to JSON values."""
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _success_body(result: EnrichedArtistProcessingResult) -> dict[str, Any]:
    """Separate frontend artist data from operational pipeline metadata."""
    return {
        "artist": result["artist"],
        "metadata": {key: value for key, value in result.items() if key != "artist"},
    }


def lambda_handler(event: Any, context: Any) -> dict[str, Any]:
    """Run the enriched-artist pipeline for an API Gateway path parameter."""
    global _cold_start
    cold_start, _cold_start = _cold_start, False
    metrics = InvocationMetrics()
    token = activate(metrics)
    pipeline_started = metrics.clock()
    request_id = getattr(context, "aws_request_id", None)
    outcome = "error"
    sources = {"theaudiodb": False, "musicbrainz": False}
    try:
        with metrics.measure("handler.validation_ms"):
            path_parameters = event.get("pathParameters") if isinstance(event, dict) else None
            artist_name = (path_parameters.get("artist_name")
                           if isinstance(path_parameters, dict) else None)
            valid = isinstance(artist_name, str) and bool(artist_name.strip())
            if valid:
                artist_name = artist_name.strip()
        if not valid:
            outcome, status, body = "validation_error", 400, {"error": "artist_name is required"}
        else:
            try:
                result = process_enriched_artist(artist_name)
                sources = result.get("sources", sources)
                outcome, status, body = "success", 200, _success_body(result)
            except _NOT_FOUND_ERRORS:
                outcome, status, body = "not_found", 404, {"error": "artist not found"}
            except (MusicBrainzError, TheAudioDBError) as error:
                logger.error("Upstream unavailable error_type=%s", type(error).__name__)
                outcome, status, body = "upstream_error", 502, {"error": "upstream service unavailable"}
            except Exception:
                # Do not attach exception text: upstream exceptions may contain
                # credential-bearing URLs or response payload fragments.
                logger.error("Unexpected artist pipeline error")
                outcome, status, body = "internal_error", 500, {"error": "internal server error"}
        with metrics.measure("response.serialization_ms"):
            response = _response(status, body)
        metrics.values["response_bytes"] = len(response["body"].encode("utf-8"))
        return response
    finally:
        metrics.add_duration("pipeline.total_ms", pipeline_started)
        metrics.values["lambda.cold_start"] = cold_start
        record = {"event": "artist_pipeline_completed", "request_id": request_id,
                  "outcome": outcome, "cold_start": cold_start,
                  "sources": sources, "metrics": metrics.snapshot()}
        logger.info(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
        deactivate(token)

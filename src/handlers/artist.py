"""AWS Lambda proxy handler for enriched artist processing."""

from dataclasses import asdict, is_dataclass
import base64
import json
import logging
from typing import Any

from src.cache.artist import (
    ArtistCacheMiss,
    ArtistCacheStale,
    load_cached_artist,
    save_artist_cache_index,
)
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
from src.utils.telemetry import InvocationMetrics, activate, deactivate, increment
from src.services.coverartarchive import (
    CoverArtError,
    CoverNotFoundError,
    cache_cover,
    get_cached_cover,
    validate_release_group_id,
)


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


def _is_cover_request(event: Any) -> bool:
    if not isinstance(event, dict):
        return False
    parameters = event.get("pathParameters")
    return isinstance(parameters, dict) and "release_group_id" in parameters


def _cover_response(event: dict[str, Any]) -> dict[str, Any]:
    value = event["pathParameters"].get("release_group_id")
    try:
        release_group_id = validate_release_group_id(value)
    except ValueError:
        return _response(400, {"error": "invalid release_group_id"})
    try:
        body, content_type = get_cached_cover(release_group_id)
    except CoverNotFoundError:
        # Lazy fill: the artist payload is returned immediately and only album
        # covers that the browser actually renders trigger CAA work.
        try:
            cache_cover(release_group_id)
            body, content_type = get_cached_cover(release_group_id)
        except CoverArtError:
            return _response(404, {"error": "cover not found"})
    except CoverArtError:
        logger.error("Private cover cache read failed")
        return _response(500, {"error": "internal server error"})
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": content_type,
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=86400",
        },
        "isBase64Encoded": True,
        "body": base64.b64encode(body).decode("ascii"),
    }


def _run_pipeline_and_publish_index(
    artist_name: str,
) -> tuple[EnrichedArtistProcessingResult, bool]:
    """Run the authoritative path, then best-effort publish its cache pointer."""
    result = process_enriched_artist(artist_name)
    try:
        save_artist_cache_index(artist_name, result)
    except Exception:
        # The cache is an optimization. Keep errors payload-free and do not turn
        # an already successful authoritative pipeline into an HTTP failure.
        increment("cache.errors")
        logger.warning("Artist cache index update failed")
        return result, False
    return result, True


def lambda_handler(event: Any, context: Any) -> dict[str, Any]:
    """Run the enriched-artist pipeline for an API Gateway path parameter."""
    if _is_cover_request(event):
        return _cover_response(event)
    global _cold_start
    cold_start, _cold_start = _cold_start, False
    metrics = InvocationMetrics()
    token = activate(metrics)
    pipeline_started = metrics.clock()
    request_id = getattr(context, "aws_request_id", None)
    outcome = "error"
    sources = {"theaudiodb": False, "musicbrainz": False}
    cache = {"status": "not_checked"}
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
                try:
                    result, cache_age = load_cached_artist(artist_name)
                    increment("cache.hits")
                    metrics.values["cache.age_seconds"] = round(cache_age, 3)
                    cache = {"status": "hit"}
                except ArtistCacheMiss:
                    increment("cache.misses")
                    cache = {"status": "miss", "reason": "not_found"}
                    result, published = _run_pipeline_and_publish_index(artist_name)
                    if not published:
                        cache["index_update"] = "error"
                except ArtistCacheStale:
                    increment("cache.stale")
                    increment("cache.misses")
                    cache = {"status": "miss", "reason": "stale"}
                    result, published = _run_pipeline_and_publish_index(artist_name)
                    if not published:
                        cache["index_update"] = "error"
                except Exception:
                    increment("cache.errors")
                    increment("cache.misses")
                    cache = {"status": "miss", "reason": "error"}
                    logger.warning("Artist cache read failed")
                    result, published = _run_pipeline_and_publish_index(artist_name)
                    if not published:
                        cache["index_update"] = "error"
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
                  "sources": sources, "cache": cache,
                  "metrics": metrics.snapshot()}
        logger.info(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
        deactivate(token)

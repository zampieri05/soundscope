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


logger = logging.getLogger(__name__)

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
    del context  # Reserved for future request metadata and tracing.

    path_parameters = event.get("pathParameters") if isinstance(event, dict) else None
    artist_name = (
        path_parameters.get("artist_name")
        if isinstance(path_parameters, dict)
        else None
    )
    if not isinstance(artist_name, str) or not artist_name.strip():
        return _response(400, {"error": "artist_name is required"})

    artist_name = artist_name.strip()
    try:
        result = process_enriched_artist(artist_name)
        return _response(200, _success_body(result))
    except _NOT_FOUND_ERRORS:
        logger.info("Artist not found: %s", artist_name)
        return _response(404, {"error": "artist not found"})
    except (MusicBrainzError, TheAudioDBError):
        logger.exception("Upstream unavailable while processing %r", artist_name)
        return _response(502, {"error": "upstream service unavailable"})
    except Exception:
        logger.exception("Unexpected error while processing artist %r", artist_name)
        return _response(500, {"error": "internal server error"})

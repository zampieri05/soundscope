"""S3 index and validated read path for recent enriched artist results."""

from datetime import datetime, timezone
import hashlib
import os
import re
from typing import Any, Callable
import unicodedata

from src.models import ArtistMember, EnrichedAlbum, EnrichedArtist
from src.pipeline.processing import EnrichedArtistProcessingResult
from src.storage.s3 import S3ObjectNotFoundError, S3StorageError, get_json, put_json
from src.utils.telemetry import measure


DEFAULT_ARTIST_CACHE_TTL_SECONDS = 24 * 60 * 60
ARTIST_CACHE_TTL_ENV = "SOUNDSCOPE_ARTIST_CACHE_TTL_SECONDS"
INDEX_VERSION = 1
_PROCESSED_KEY_PATTERN = re.compile(
    r"processed/enriched/artists/[^/]+/\d{8}T\d{12}Z\.json"
)


class ArtistCacheMiss(Exception):
    """No index exists for the normalized artist search."""


class ArtistCacheStale(Exception):
    """The index exists but is older than the logical TTL."""


class ArtistCacheError(Exception):
    """The cache cannot safely produce a schema-compatible result."""


def _configured_ttl() -> int:
    raw = os.getenv(ARTIST_CACHE_TTL_ENV, "").strip()
    if not raw:
        return DEFAULT_ARTIST_CACHE_TTL_SECONDS
    try:
        value = int(raw)
    except ValueError as exc:
        raise ArtistCacheError("TTL de cache configurado é inválido.") from exc
    if value < 0:
        raise ArtistCacheError("TTL de cache configurado é inválido.")
    return value


ARTIST_CACHE_TTL_SECONDS = DEFAULT_ARTIST_CACHE_TTL_SECONDS


def normalize_artist_search(name: str) -> str:
    """Apply conservative Unicode, case and whitespace normalization."""
    if not isinstance(name, str) or not name.strip():
        raise ArtistCacheError("Nome de busca inválido para cache.")
    normalized = unicodedata.normalize("NFKC", name)
    return " ".join(normalized.split()).casefold()


def _index_key(name: str) -> str:
    digest = hashlib.sha256(normalize_artist_search(name).encode("utf-8")).hexdigest()
    return f"cache/artist-search/v1/{digest}.json"


def _valid_processed_key(value: Any) -> bool:
    return isinstance(value, str) and bool(_PROCESSED_KEY_PATTERN.fullmatch(value))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _metadata(result: EnrichedArtistProcessingResult) -> dict[str, Any]:
    """Keep only the safe operational fields needed to reproduce the response."""
    allowed = {
        "artist_name", "theaudiodb_artist_id", "musicbrainz_mbid", "source",
        "sources", "theaudiodb_raw_s3_key", "musicbrainz_raw_s3_key",
        "processed_s3_key",
    }
    return {key: value for key, value in result.items() if key in allowed}


def save_artist_cache_index(
    artist_name: str,
    result: EnrichedArtistProcessingResult,
    *,
    now: datetime | None = None,
    put: Callable[..., None] = put_json,
) -> str:
    """Publish an index only for an already-persisted processed result."""
    processed_key = result.get("processed_s3_key")
    if not _valid_processed_key(processed_key):
        raise ArtistCacheError("Resultado não possui referência processed válida.")
    moment = now or _utc_now()
    if not isinstance(moment, datetime) or moment.tzinfo is None:
        raise ArtistCacheError("Instante do índice deve possuir fuso horário.")
    key = _index_key(artist_name)
    document = {
        "version": INDEX_VERSION,
        "processed_s3_key": processed_key,
        "cached_at": moment.astimezone(timezone.utc).isoformat(),
        "metadata": _metadata(result),
    }
    try:
        put(key, document)
    except S3StorageError as exc:
        raise ArtistCacheError("Falha ao publicar índice do cache.") from exc
    return key


def _text(value: Any, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str):
        raise ArtistCacheError("Processed possui schema incompatível.")
    return value


def _load_artist(document: Any) -> EnrichedArtist:
    if not isinstance(document, dict):
        raise ArtistCacheError("Processed possui schema incompatível.")
    required = {"name", "country", "genre", "formed_year", "biography",
                "image_url", "source_ids", "members", "albums"}
    if not required.issubset(document):
        raise ArtistCacheError("Processed possui schema incompatível.")
    source_ids = document["source_ids"]
    if (not isinstance(source_ids, dict) or not source_ids or
            any(not isinstance(k, str) or not isinstance(v, str) or not v.strip()
                for k, v in source_ids.items())):
        raise ArtistCacheError("Processed possui source_ids incompatível.")
    members_raw, albums_raw = document["members"], document["albums"]
    if not isinstance(members_raw, list) or not isinstance(albums_raw, list):
        raise ArtistCacheError("Processed possui coleções incompatíveis.")
    try:
        members = [ArtistMember(
            name=_text(item["name"]),
            role=_text(item.get("role"), optional=True),
            active=(item.get("active") if isinstance(item.get("active"), bool)
                    or item.get("active") is None else _invalid()),
        ) for item in members_raw if _mapping(item)]
        albums = [EnrichedAlbum(
            title=_text(item["title"]),
            year=_text(item.get("year"), optional=True),
            album_id=_text(item.get("album_id"), optional=True),
            musicbrainz_release_group_id=_text(
                item.get("musicbrainz_release_group_id"), optional=True),
            cover_url=_text(item.get("cover_url"), optional=True),
            primary_type=_text(item.get("primary_type"), optional=True),
            secondary_types=_string_list(item.get("secondary_types")),
            first_release_date=_text(item.get("first_release_date"), optional=True),
        ) for item in albums_raw if _mapping(item)]
        return EnrichedArtist(
            name=_text(document["name"]),
            country=_text(document["country"], optional=True),
            genre=_text(document["genre"], optional=True),
            formed_year=_text(document["formed_year"], optional=True),
            biography=_text(document["biography"], optional=True),
            image_url=_text(document["image_url"], optional=True),
            source_ids=dict(source_ids), members=members, albums=albums,
        )
    except (KeyError, TypeError) as exc:
        raise ArtistCacheError("Processed possui schema incompatível.") from exc


def _mapping(value: Any) -> bool:
    if not isinstance(value, dict):
        raise ArtistCacheError("Processed possui item incompatível.")
    return True


def _invalid() -> Any:
    raise ArtistCacheError("Processed possui valor incompatível.")


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ArtistCacheError("Processed possui lista incompatível.")
    return list(value)


def _validate_index(index: Any) -> tuple[str, datetime, dict[str, Any]]:
    if not isinstance(index, dict) or index.get("version") != INDEX_VERSION:
        raise ArtistCacheError("Índice possui schema incompatível.")
    key, cached_at, metadata = (index.get("processed_s3_key"),
                                index.get("cached_at"), index.get("metadata"))
    if not _valid_processed_key(key) or not isinstance(metadata, dict):
        raise ArtistCacheError("Índice possui referência incompatível.")
    try:
        moment = datetime.fromisoformat(cached_at)
    except (TypeError, ValueError) as exc:
        raise ArtistCacheError("Índice possui freshness incompatível.") from exc
    if moment.tzinfo is None:
        raise ArtistCacheError("Índice possui freshness incompatível.")
    required_metadata = {
        "artist_name", "theaudiodb_artist_id", "musicbrainz_mbid", "source",
        "sources", "theaudiodb_raw_s3_key", "musicbrainz_raw_s3_key",
        "processed_s3_key",
    }
    if set(metadata) != required_metadata:
        raise ArtistCacheError("Índice possui metadata incompatível.")
    if (not isinstance(metadata["artist_name"], str) or
            not isinstance(metadata["source"], str) or
            any(value is not None and not isinstance(value, str) for value in (
                metadata["theaudiodb_artist_id"], metadata["musicbrainz_mbid"],
                metadata["theaudiodb_raw_s3_key"],
                metadata["musicbrainz_raw_s3_key"]))):
        raise ArtistCacheError("Índice possui metadata incompatível.")
    sources = metadata["sources"]
    if (not isinstance(sources, dict) or
            set(sources) != {"theaudiodb", "musicbrainz"} or
            any(not isinstance(value, bool) for value in sources.values())):
        raise ArtistCacheError("Índice possui sources incompatível.")
    return key, moment.astimezone(timezone.utc), metadata


def load_cached_artist(
    artist_name: str,
    *,
    now: datetime | None = None,
    get: Callable[..., Any] = get_json,
) -> tuple[EnrichedArtistProcessingResult, float]:
    """Resolve the exact search index and validate its processed document."""
    moment = now or _utc_now()
    try:
        with measure("cache.lookup_ms"):
            index = get(_index_key(artist_name))
    except S3ObjectNotFoundError as exc:
        raise ArtistCacheMiss() from exc
    except S3StorageError as exc:
        raise ArtistCacheError("Falha na leitura do índice.") from exc
    processed_key, cached_at, metadata = _validate_index(index)
    age = max(0.0, (moment.astimezone(timezone.utc) - cached_at).total_seconds())
    if age > _configured_ttl():
        raise ArtistCacheStale()
    try:
        with measure("cache.processed_read_ms"):
            document = get(processed_key)
    except (S3ObjectNotFoundError, S3StorageError) as exc:
        raise ArtistCacheError("Falha na leitura do processed.") from exc
    artist = _load_artist(document)
    expected_key = metadata.get("processed_s3_key")
    if expected_key != processed_key:
        raise ArtistCacheError("Índice e metadata divergem.")
    if (metadata["theaudiodb_artist_id"] != artist.source_ids.get("theaudiodb") or
            metadata["musicbrainz_mbid"] != artist.source_ids.get("musicbrainz")):
        raise ArtistCacheError("Índice e processed divergem.")
    result: EnrichedArtistProcessingResult = {"artist": artist}
    result.update(metadata)
    return result, age

"""Transformação específica do documento RAW de detalhes do MusicBrainz."""

from typing import Any

from src.models import NormalizedArtist
from src.pipeline.transformers.errors import TransformationError


def _optional_text(value: Any) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def _required_text(raw_data: dict[str, Any], field: str) -> str:
    value = _optional_text(raw_data.get(field))
    if value is None:
        raise TransformationError(f'O campo obrigatório "{field}" está ausente.')
    return value


def _first_genre(raw_data: dict[str, Any]) -> str | None:
    genres = raw_data.get("genres")
    if not isinstance(genres, list):
        return None
    for genre in genres:
        if isinstance(genre, dict):
            name = _optional_text(genre.get("name"))
            if name is not None:
                return name
    return None


def _formed_year(raw_data: dict[str, Any]) -> str | None:
    life_span = raw_data.get("life-span")
    if not isinstance(life_span, dict):
        return None
    begin = _optional_text(life_span.get("begin"))
    return begin[:4] if begin and len(begin) >= 4 and begin[:4].isdigit() else None


def transform_musicbrainz_artist(raw_data: Any) -> NormalizedArtist:
    """Normaliza o RAW retornado por ``get_artist_details`` sem alterá-lo."""
    if not isinstance(raw_data, dict):
        raise TransformationError("O RAW do MusicBrainz deve ser um objeto JSON.")

    return NormalizedArtist(
        source="musicbrainz",
        source_artist_id=_required_text(raw_data, "id"),
        name=_required_text(raw_data, "name"),
        country=_optional_text(raw_data.get("country")),
        genre=_first_genre(raw_data),
        formed_year=_formed_year(raw_data),
        biography=None,
        image_url=None,
    )

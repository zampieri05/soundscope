"""Transformação específica do documento RAW de detalhes do MusicBrainz."""

from typing import Any

from src.models import ArtistMember, EnrichedAlbum, NormalizedArtist
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


def transform_musicbrainz_members(raw_data: Any) -> list[ArtistMember]:
    """Extrai relações explícitas de integrantes, sem inferir dados ausentes."""
    if not isinstance(raw_data, dict):
        raise TransformationError("O RAW do MusicBrainz deve ser um objeto JSON.")
    result: list[ArtistMember] = []
    seen: set[str] = set()
    relations = raw_data.get("relations", [])
    if not isinstance(relations, list):
        return result
    for relation in relations:
        if not isinstance(relation, dict) or relation.get("type") != "member of band":
            continue
        related = relation.get("artist")
        name = (
            _optional_text(related.get("name")) if isinstance(related, dict) else None
        )
        if not name or name.casefold() in seen:
            continue
        attributes = relation.get("attributes")
        roles = (
            [
                value.strip()
                for value in attributes
                if isinstance(value, str) and value.strip()
            ]
            if isinstance(attributes, list)
            else []
        )
        ended = relation.get("ended")
        result.append(
            ArtistMember(
                name,
                " / ".join(roles) or None,
                not ended if isinstance(ended, bool) else None,
            )
        )
        seen.add(name.casefold())
    return result


def transform_musicbrainz_albums(raw_data: Any) -> list[EnrichedAlbum]:
    """Normaliza release groups de álbuns retornados pelo MusicBrainz."""
    if not isinstance(raw_data, dict) or not isinstance(
        raw_data.get("release-groups"), list
    ):
        raise TransformationError("O campo 'release-groups' deve ser uma lista.")
    result: list[EnrichedAlbum] = []
    for group in raw_data["release-groups"]:
        if not isinstance(group, dict) or group.get("primary-type") not in (
            None,
            "Album",
        ):
            continue
        title, group_id = _optional_text(group.get("title")), _optional_text(
            group.get("id")
        )
        if not title or not group_id:
            continue
        date = _optional_text(group.get("first-release-date"))
        year = date[:4] if date and date[:4].isdigit() else None
        result.append(
            EnrichedAlbum(
                title,
                year,
                None,
                group_id,
                f"https://coverartarchive.org/release-group/{group_id}/front-500",
            )
        )
    return result

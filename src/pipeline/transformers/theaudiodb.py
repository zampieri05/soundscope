"""Transformações específicas dos documentos RAW do TheAudioDB."""

from typing import Any

from src.models import NormalizedAlbum, NormalizedArtist
from src.pipeline.transformers.errors import TransformationError


def _optional_text(value: Any) -> str | None:
    """Remove espaços de textos e representa valores vazios como ausentes."""
    return value.strip() or None if isinstance(value, str) else None


def _required_text(record: dict[str, Any], field: str) -> str:
    value = _optional_text(record.get(field))
    if value is None:
        raise TransformationError(f'O campo obrigatório "{field}" está ausente.')
    return value


def transform_theaudiodb_artist(raw_data: Any) -> NormalizedArtist:
    """Normaliza o primeiro artista da resposta de ``search_artist``.

    A ordem da API é preservada: o primeiro resultado é o artista selecionado.
    Somente leituras são feitas no documento recebido.
    """
    if not isinstance(raw_data, dict):
        raise TransformationError("O RAW do TheAudioDB deve ser um objeto JSON.")
    artists = raw_data.get("artists")
    if not isinstance(artists, list) or not artists or not isinstance(artists[0], dict):
        raise TransformationError("O RAW deve conter uma lista 'artists' não vazia.")

    artist = artists[0]
    return NormalizedArtist(
        source="theaudiodb",
        source_artist_id=_required_text(artist, "idArtist"),
        name=_required_text(artist, "strArtist"),
        country=_optional_text(artist.get("strCountry")),
        genre=_optional_text(artist.get("strGenre")),
        formed_year=_optional_text(artist.get("intFormedYear")),
        biography=_optional_text(artist.get("strBiographyEN")),
        image_url=_optional_text(artist.get("strArtistThumb")),
    )


def transform_theaudiodb_albums(raw_data: Any) -> list[NormalizedAlbum]:
    """Normaliza a lista de álbuns retornada por ``search_albums``."""
    if not isinstance(raw_data, dict):
        raise TransformationError("O RAW do TheAudioDB deve ser um objeto JSON.")
    albums = raw_data.get("album")
    if albums is None:
        return []
    if not isinstance(albums, list):
        raise TransformationError("O campo 'album' deve ser uma lista ou null.")

    normalized = []
    for album in albums:
        if not isinstance(album, dict):
            raise TransformationError("Cada álbum deve ser um objeto JSON.")
        normalized.append(
            NormalizedAlbum(
                source="theaudiodb",
                source_album_id=_required_text(album, "idAlbum"),
                source_artist_id=_required_text(album, "idArtist"),
                name=_required_text(album, "strAlbum"),
                release_year=_optional_text(album.get("intYearReleased")),
                cover_url=_optional_text(album.get("strAlbumThumb")),
            )
        )
    return normalized

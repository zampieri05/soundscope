"""Regras determinísticas para enriquecer artistas normalizados."""

from typing import TypeVar

from src.models import (
    ArtistMember,
    EnrichedAlbum,
    EnrichedArtist,
    NormalizedAlbum,
    NormalizedArtist,
)
from src.pipeline.enrichment.errors import ArtistEnrichmentError

T = TypeVar("T")


def _comparable_name(name: str) -> str:
    """Ignora caixa e espaços extras, sem tentar fazer fuzzy matching."""
    return " ".join(name.split()).casefold()


def _prefer(preferred: T | None, fallback: T | None) -> T | None:
    """Seleciona o valor preferencial, considerando texto vazio ausente."""
    if preferred is not None and (
        not isinstance(preferred, str) or bool(preferred.strip())
    ):
        return preferred
    if fallback is not None and (
        not isinstance(fallback, str) or bool(fallback.strip())
    ):
        return fallback
    return None


def enrich_artist(
    theaudiodb_artist: NormalizedArtist,
    musicbrainz_artist: NormalizedArtist,
    theaudiodb_albums: list[NormalizedAlbum] | None = None,
    musicbrainz_albums: list[EnrichedAlbum] | None = None,
    members: list[ArtistMember] | None = None,
) -> EnrichedArtist:
    """Cria uma visão enriquecida sem modificar os registros de entrada.

    MusicBrainz tem prioridade para país e ano de formação. TheAudioDB tem
    prioridade para gênero, biografia e imagem, que são atributos mais ricos
    nessa integração. Todo campo usa a outra fonte como fallback.
    """
    if not isinstance(theaudiodb_artist, NormalizedArtist) or not isinstance(
        musicbrainz_artist, NormalizedArtist
    ):
        raise ArtistEnrichmentError("O enrichment requer dois NormalizedArtist.")
    if theaudiodb_artist.source != "theaudiodb":
        raise ArtistEnrichmentError(
            "O argumento theaudiodb_artist deve ter source='theaudiodb'."
        )
    if musicbrainz_artist.source != "musicbrainz":
        raise ArtistEnrichmentError(
            "O argumento musicbrainz_artist deve ter source='musicbrainz'."
        )
    if _comparable_name(theaudiodb_artist.name) != _comparable_name(
        musicbrainz_artist.name
    ):
        raise ArtistEnrichmentError(
            "Não é possível enriquecer artistas com nomes diferentes."
        )

    albums = _merge_albums(theaudiodb_albums or [], musicbrainz_albums or [])
    return EnrichedArtist(
        name=theaudiodb_artist.name,
        country=_prefer(musicbrainz_artist.country, theaudiodb_artist.country),
        genre=_prefer(theaudiodb_artist.genre, musicbrainz_artist.genre),
        formed_year=_prefer(
            musicbrainz_artist.formed_year, theaudiodb_artist.formed_year
        ),
        biography=_prefer(theaudiodb_artist.biography, musicbrainz_artist.biography),
        image_url=_prefer(theaudiodb_artist.image_url, musicbrainz_artist.image_url),
        source_ids={
            "theaudiodb": theaudiodb_artist.source_artist_id,
            "musicbrainz": musicbrainz_artist.source_artist_id,
        },
        members=list(members or []),
        albums=albums,
    )


def _album_key(title: str, year: str | None) -> tuple[str, str]:
    return (" ".join(title.split()).casefold(), year or "")


def _merge_albums(
    theaudiodb_albums: list[NormalizedAlbum],
    musicbrainz_albums: list[EnrichedAlbum],
) -> list[EnrichedAlbum]:
    """Une catálogos, mantendo metadados do TheAudioDB e IDs complementares."""
    merged: dict[tuple[str, str], EnrichedAlbum] = {}
    for album in theaudiodb_albums:
        item = EnrichedAlbum(
            album.name, album.release_year, album.source_album_id, None, album.cover_url
        )
        merged[_album_key(item.title, item.year)] = item
    for album in musicbrainz_albums:
        key = _album_key(album.title, album.year)
        current = merged.get(key)
        if current:
            merged[key] = EnrichedAlbum(
                current.title,
                current.year,
                current.album_id,
                album.musicbrainz_release_group_id,
                current.cover_url or album.cover_url,
            )
        else:
            merged[key] = album
    return sorted(
        merged.values(),
        key=lambda item: (item.year is None, item.year or "", item.title.casefold()),
    )[:20]

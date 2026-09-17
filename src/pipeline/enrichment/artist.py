"""Regras determinísticas para enriquecer artistas normalizados."""

from typing import TypeVar
import re
import unicodedata

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
    """Normaliza Unicode, diacríticos, caixa, pontuação básica e espaços."""
    decomposed = unicodedata.normalize("NFKD", name)
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^\w]+", " ", plain.casefold()).split())


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


def partial_artist(
    artist: NormalizedArtist,
    albums: list[NormalizedAlbum] | list[EnrichedAlbum] | None = None,
    members: list[ArtistMember] | None = None,
) -> EnrichedArtist:
    """Converte uma única fonte em perfil parcial sem fabricar campos."""
    enriched_albums = (
        _merge_albums(albums, [])  # type: ignore[arg-type]
        if artist.source == "theaudiodb"
        else list(albums or [])
    )
    return EnrichedArtist(
        artist.name, artist.country, artist.genre, artist.formed_year,
        artist.biography, artist.image_url,
        {artist.source: artist.source_artist_id}, list(members or []),
        enriched_albums,
    )


def _album_key(title: str, year: str | None) -> tuple[str, str]:
    return (_comparable_name(title), year or "")


def _merge_albums(
    theaudiodb_albums: list[NormalizedAlbum],
    musicbrainz_albums: list[EnrichedAlbum],
) -> list[EnrichedAlbum]:
    """Une catálogos, mantendo metadados do TheAudioDB e IDs complementares."""
    merged: dict[tuple[str, ...], EnrichedAlbum] = {}
    for album in theaudiodb_albums:
        item = EnrichedAlbum(
            album.name, album.release_year, album.source_album_id, None, album.cover_url
        )
        merged[("tadb", album.source_album_id)] = item
    for album in musicbrainz_albums:
        exact_key = ("mb", album.musicbrainz_release_group_id) if album.musicbrainz_release_group_id else None
        fallback_key = ("metadata",) + _album_key(album.title, album.year)
        current_key = next((key for key, value in merged.items()
                            if not value.musicbrainz_release_group_id
                            and _album_key(value.title, value.year) == _album_key(album.title, album.year)), None)
        current = merged.get(current_key) if current_key else None
        if current:
            merged[current_key] = EnrichedAlbum(
                current.title,
                current.year,
                current.album_id,
                album.musicbrainz_release_group_id,
                current.cover_url or album.cover_url,
                album.primary_type, album.secondary_types, album.first_release_date,
            )
        else:
            merged[exact_key or fallback_key] = album
    return sorted(
        merged.values(),
        key=lambda item: (item.year is None, item.year or "", item.title.casefold()),
    )

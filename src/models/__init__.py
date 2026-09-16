"""Modelos normalizados do domínio musical."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NormalizedArtist:
    """Representação pequena e independente da fonte para um artista."""

    source: str
    source_artist_id: str
    name: str
    country: str | None = None
    genre: str | None = None
    formed_year: str | None = None
    biography: str | None = None
    image_url: str | None = None


@dataclass(frozen=True)
class NormalizedAlbum:
    """Representação normalizada de um álbum extraído do TheAudioDB."""

    source: str
    source_album_id: str
    source_artist_id: str
    name: str
    release_year: str | None = None
    cover_url: str | None = None


@dataclass(frozen=True)
class ArtistMember:
    name: str
    role: str | None = None
    active: bool | None = None


@dataclass(frozen=True)
class EnrichedAlbum:
    title: str
    year: str | None = None
    album_id: str | None = None
    musicbrainz_release_group_id: str | None = None
    cover_url: str | None = None


@dataclass(frozen=True)
class EnrichedArtist:
    """Visão consolidada de um artista, com rastreabilidade das fontes."""

    name: str
    country: str | None
    genre: str | None
    formed_year: str | None
    biography: str | None
    image_url: str | None
    source_ids: dict[str, str]
    members: list[ArtistMember] = field(default_factory=list)
    albums: list[EnrichedAlbum] = field(default_factory=list)

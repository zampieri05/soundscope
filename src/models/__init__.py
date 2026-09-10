"""Modelos normalizados do domínio musical."""

from dataclasses import dataclass


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

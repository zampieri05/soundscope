"""Transformação conservadora de artista Last.fm para o domínio SoundScope."""

import re
from typing import Any

from src.models import NormalizedArtist


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def transform_lastfm_artist(raw: dict[str, Any]) -> NormalizedArtist:
    artist = raw.get("artist")
    if not isinstance(artist, dict):
        raise ValueError("Resposta Last.fm sem artista utilizável.")
    name = _text(artist.get("name"))
    if not name:
        raise ValueError("Resposta Last.fm sem nome de artista.")

    tags_raw = artist.get("tags", {}).get("tag", [])
    tags = [
        item.get("name").strip()
        for item in tags_raw
        if isinstance(item, dict) and isinstance(item.get("name"), str) and item.get("name").strip()
    ]
    bio = artist.get("bio", {})
    biography = _text(bio.get("content")) or _text(bio.get("summary"))
    if biography:
        biography = re.sub(r"\s*<a\b[^>]*>.*?</a>\s*$", "", biography, flags=re.I | re.S).strip()

    images = artist.get("image")
    image_url = None
    if isinstance(images, list):
        for item in reversed(images):
            if isinstance(item, dict) and _text(item.get("#text")):
                image_url = item["#text"].strip()
                break

    mbid = _text(artist.get("mbid"))
    # Last.fm não expõe um ID próprio estável no getInfo; a URL canônica serve
    # como provenance ID sem fingir que é MBID.
    source_id = _text(artist.get("url")) or f"lastfm:{name.casefold()}"

    return NormalizedArtist(
        source="lastfm",
        source_artist_id=source_id,
        name=name,
        genre=", ".join(tags[:5]) if tags else None,
        biography=biography,
        image_url=image_url,
        musicbrainz_id=mbid,
    )

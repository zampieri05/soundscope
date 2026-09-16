"""Transformações de JSON RAW em modelos normalizados do SoundScope."""

from src.pipeline.transformers.musicbrainz import (
    transform_musicbrainz_albums,
    transform_musicbrainz_artist,
    transform_musicbrainz_members,
)
from src.pipeline.transformers.theaudiodb import (
    transform_theaudiodb_albums,
    transform_theaudiodb_artist,
)

__all__ = [
    "transform_musicbrainz_artist",
    "transform_musicbrainz_albums",
    "transform_musicbrainz_members",
    "transform_theaudiodb_albums",
    "transform_theaudiodb_artist",
]

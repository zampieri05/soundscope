"""Orquestração da extração e persistência de documentos RAW."""

from src.pipeline.ingestion.errors import (
    IngestionError,
    InvalidIngestionResponseError,
    UsableArtistNotFoundError,
)
from src.pipeline.ingestion.theaudiodb import (
    TheAudioDBArtistIngestionResult,
    ingest_theaudiodb_artist,
)

__all__ = [
    "IngestionError",
    "InvalidIngestionResponseError",
    "TheAudioDBArtistIngestionResult",
    "UsableArtistNotFoundError",
    "ingest_theaudiodb_artist",
]

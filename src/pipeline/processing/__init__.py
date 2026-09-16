"""Orquestração dos fluxos até a camada processada."""

from src.pipeline.processing.enriched import (
    EnrichedArtistProcessingResult,
    process_enriched_artist,
)
from src.pipeline.processing.theaudiodb import (
    TheAudioDBArtistProcessingResult,
    process_theaudiodb_artist,
)

__all__ = [
    "EnrichedArtistProcessingResult",
    "TheAudioDBArtistProcessingResult",
    "process_enriched_artist",
    "process_theaudiodb_artist",
]

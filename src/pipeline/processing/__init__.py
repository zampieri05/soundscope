"""Orquestração dos fluxos até a camada processada."""

from src.pipeline.processing.theaudiodb import (
    TheAudioDBArtistProcessingResult,
    process_theaudiodb_artist,
)

__all__ = ["TheAudioDBArtistProcessingResult", "process_theaudiodb_artist"]

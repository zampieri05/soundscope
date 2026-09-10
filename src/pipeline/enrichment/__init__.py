"""Combinação de modelos normalizados em registros enriquecidos."""

from src.pipeline.enrichment.artist import enrich_artist
from src.pipeline.enrichment.errors import ArtistEnrichmentError

__all__ = ["ArtistEnrichmentError", "enrich_artist"]

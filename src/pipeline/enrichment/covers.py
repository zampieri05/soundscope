"""Enriquecimento best-effort e com orçamento fixo de capas."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from src.models import EnrichedAlbum
from src.services.coverartarchive import front_cover_url

MAX_CAA_LOOKUPS = 12
MAX_CAA_WORKERS = 4


def enrich_missing_covers(albums: list[EnrichedAlbum]) -> list[EnrichedAlbum]:
    """Consulta no máximo 12 MBIDs em paralelo e nunca remove capas existentes."""
    candidates = [
        (index, album.musicbrainz_release_group_id)
        for index, album in enumerate(albums)
        if not album.cover_url and album.musicbrainz_release_group_id
    ][:MAX_CAA_LOOKUPS]
    if not candidates:
        return list(albums)
    covers: dict[int, str] = {}
    try:
        with ThreadPoolExecutor(max_workers=MAX_CAA_WORKERS) as executor:
            results = executor.map(front_cover_url, (mbid for _, mbid in candidates))
            for (index, _), cover in zip(candidates, results):
                if cover:
                    covers[index] = cover
    except Exception:
        # CAA é opcional; inclusive falhas inesperadas nunca invalidam o perfil.
        return list(albums)
    return [replace(album, cover_url=covers[index]) if index in covers else album
            for index, album in enumerate(albums)]

"""Orquestração da ingestão RAW de artistas do TheAudioDB."""

from typing import Any, TypedDict

from src.pipeline.ingestion.errors import (
    InvalidIngestionResponseError,
    UsableArtistNotFoundError,
)
from src.services.theaudiodb.client import search_artist
from src.storage.s3 import save_raw_json

SOURCE = "theaudiodb"
ENTITY_TYPE = "artists"


class TheAudioDBArtistIngestionResult(TypedDict):
    """Referência pequena ao documento RAW persistido."""

    artist_name: str
    artist_id: str
    source: str
    raw_s3_key: str


def _first_artist_id(raw: Any) -> str:
    """Obtém o primeiro ``idArtist`` utilizável sem modificar o RAW."""
    if not isinstance(raw, dict) or "artists" not in raw:
        raise InvalidIngestionResponseError(
            "O TheAudioDB retornou uma resposta sem a lista artists."
        )

    artists = raw["artists"]
    if not isinstance(artists, list):
        raise InvalidIngestionResponseError(
            "O campo artists da resposta do TheAudioDB deve ser uma lista."
        )

    for artist in artists:
        if not isinstance(artist, dict):
            continue
        artist_id = artist.get("idArtist")
        if isinstance(artist_id, str) and artist_id.strip():
            return artist_id

    raise UsableArtistNotFoundError(
        "A resposta do TheAudioDB não contém artista com idArtist utilizável."
    )


def ingest_theaudiodb_artist(
    artist_name: str,
) -> TheAudioDBArtistIngestionResult:
    """Extrai um artista do TheAudioDB e persiste seu documento RAW no S3.

    Validação do nome, comunicação HTTP e persistência permanecem sob
    responsabilidade dos componentes existentes. Os erros desses componentes
    são propagados sem conversão para preservar suas APIs e causas originais.
    """
    raw = search_artist(artist_name)
    artist_id = _first_artist_id(raw)
    raw_s3_key = save_raw_json(SOURCE, raw, ENTITY_TYPE, artist_id)

    return {
        "artist_name": artist_name,
        "artist_id": artist_id,
        "source": SOURCE,
        "raw_s3_key": raw_s3_key,
    }

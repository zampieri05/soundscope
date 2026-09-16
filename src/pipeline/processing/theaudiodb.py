"""Pipeline de artista do TheAudioDB até a camada processada."""

from dataclasses import asdict
from typing import TypedDict

from src.models import NormalizedArtist
from src.pipeline.ingestion.theaudiodb import ENTITY_TYPE, SOURCE, _first_artist_id
from src.pipeline.transformers import transform_theaudiodb_artist
from src.services.theaudiodb.client import search_artist
from src.storage.s3 import save_processed_json, save_raw_json


class TheAudioDBArtistProcessingResult(TypedDict):
    """Referências aos dois documentos produzidos pelo pipeline."""

    artist_name: str
    artist_id: str
    source: str
    raw_s3_key: str
    processed_s3_key: str


def process_theaudiodb_artist(
    artist_name: str,
) -> TheAudioDBArtistProcessingResult:
    """Extrai, preserva, transforma e persiste um artista do TheAudioDB.

    As operações são deliberadamente sequenciais: o RAW é persistido antes
    que a transformação seja iniciada. Exceções dos componentes são propagadas
    para que uma execução parcial nunca seja reportada como sucesso.
    """
    raw = search_artist(artist_name)
    artist_id = _first_artist_id(raw)
    raw_s3_key = save_raw_json(SOURCE, raw, ENTITY_TYPE, artist_id)

    normalized = transform_theaudiodb_artist(raw)
    if not isinstance(normalized, NormalizedArtist):
        raise TypeError("O transformer deve retornar um NormalizedArtist.")
    processed_document = asdict(normalized)
    processed_s3_key = save_processed_json(
        processed_document, ENTITY_TYPE, artist_id
    )

    return {
        "artist_name": artist_name,
        "artist_id": artist_id,
        "source": SOURCE,
        "raw_s3_key": raw_s3_key,
        "processed_s3_key": processed_s3_key,
    }

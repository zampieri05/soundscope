"""Orquestração multi-source de artistas enriquecidos."""

from dataclasses import asdict
from typing import Any, TypedDict

from src.models import EnrichedArtist, NormalizedArtist
from src.pipeline.enrichment import enrich_artist
from src.pipeline.ingestion.theaudiodb import _first_artist_id
from src.pipeline.transformers import (
    transform_musicbrainz_albums,
    transform_musicbrainz_artist,
    transform_musicbrainz_members,
    transform_theaudiodb_albums,
    transform_theaudiodb_artist,
)
from src.services.musicbrainz import client as musicbrainz_client
from src.services.theaudiodb import client as theaudiodb_client
from src.storage.dynamodb import save_enriched_artist
from src.storage.s3 import save_processed_json, save_raw_json


class EnrichedArtistProcessingResult(TypedDict):
    """Artista enriquecido e rastreabilidade produzidos pelo pipeline."""

    artist: EnrichedArtist
    artist_name: str
    theaudiodb_artist_id: str
    musicbrainz_mbid: str
    source: str
    theaudiodb_raw_s3_key: str
    musicbrainz_raw_s3_key: str
    processed_s3_key: str


def _first_musicbrainz_artist(search_raw: Any) -> dict[str, Any]:
    """Seleciona deterministicamente o primeiro resultado com nome utilizável."""
    if isinstance(search_raw, dict) and isinstance(search_raw.get("artists"), list):
        for artist in search_raw["artists"]:
            if (
                isinstance(artist, dict)
                and isinstance(artist.get("name"), str)
                and artist["name"].strip()
            ):
                return artist
    raise musicbrainz_client.ArtistNotFoundError(
        "A busca do MusicBrainz não retornou um artista utilizável."
    )


def _musicbrainz_id(artist: dict[str, Any]) -> str:
    mbid = artist.get("id")
    if not isinstance(mbid, str) or not mbid.strip():
        raise musicbrainz_client.MusicBrainzError(
            "O resultado do MusicBrainz não contém um MBID utilizável."
        )
    return mbid.strip()


def process_enriched_artist(artist_name: str) -> EnrichedArtistProcessingResult:
    """Extrai duas fontes, normaliza, enriquece e persiste o resultado.

    Cada operação ocorre apenas após a anterior ter sucesso. As exceções das
    camadas especializadas são propagadas e nenhuma execução parcial é
    apresentada ao chamador como concluída.
    """
    theaudiodb_raw = theaudiodb_client.search_artist(artist_name)
    theaudiodb_id = _first_artist_id(theaudiodb_raw)
    theaudiodb_raw_key = save_raw_json(
        "theaudiodb", theaudiodb_raw, "artists", theaudiodb_id
    )
    theaudiodb_artist = transform_theaudiodb_artist(theaudiodb_raw)
    if not isinstance(theaudiodb_artist, NormalizedArtist):
        raise TypeError("O transformer do TheAudioDB deve retornar NormalizedArtist.")

    extended_catalog = isinstance(
        getattr(theaudiodb_client, "AlbumsNotFoundError", None), type
    )
    if not extended_catalog:
        theaudiodb_albums = []
    else:
        try:
            theaudiodb_albums_raw = theaudiodb_client.search_albums(theaudiodb_id)
            save_raw_json("theaudiodb", theaudiodb_albums_raw, "albums", theaudiodb_id)
            theaudiodb_albums = transform_theaudiodb_albums(theaudiodb_albums_raw)
        except theaudiodb_client.AlbumsNotFoundError:
            theaudiodb_albums = []

    musicbrainz_search_raw = musicbrainz_client.search_artist(artist_name)
    musicbrainz_match = _first_musicbrainz_artist(musicbrainz_search_raw)
    mbid = _musicbrainz_id(musicbrainz_match)
    # A busca também é uma resposta externa utilizada pelo pipeline. Ela é
    # preservada antes da consulta de detalhes; a chave retornada ao chamador é
    # a do documento de detalhes efetivamente entregue ao transformer.
    save_raw_json("musicbrainz", musicbrainz_search_raw, "artists", mbid)
    musicbrainz_details_raw = musicbrainz_client.get_artist_details(mbid)
    musicbrainz_raw_key = save_raw_json(
        "musicbrainz", musicbrainz_details_raw, "artists", mbid
    )
    musicbrainz_artist = transform_musicbrainz_artist(musicbrainz_details_raw)
    if not isinstance(musicbrainz_artist, NormalizedArtist):
        raise TypeError("O transformer do MusicBrainz deve retornar NormalizedArtist.")

    members = transform_musicbrainz_members(musicbrainz_details_raw)
    if extended_catalog:
        musicbrainz_albums_raw = musicbrainz_client.get_release_groups(mbid)
        save_raw_json("musicbrainz", musicbrainz_albums_raw, "release-groups", mbid)
        musicbrainz_albums = transform_musicbrainz_albums(musicbrainz_albums_raw)
    else:
        musicbrainz_albums = []

    if extended_catalog:
        enriched = enrich_artist(
            theaudiodb_artist,
            musicbrainz_artist,
            theaudiodb_albums,
            musicbrainz_albums,
            members,
        )
    else:
        enriched = enrich_artist(theaudiodb_artist, musicbrainz_artist)
    if not isinstance(enriched, EnrichedArtist):
        raise TypeError("O enrichment deve retornar um EnrichedArtist.")
    serialized = asdict(enriched)
    if not extended_catalog:
        serialized.pop("members", None)
        serialized.pop("albums", None)
    processed_key = save_processed_json(
        serialized, "artists", theaudiodb_id, data_type="enriched"
    )
    save_enriched_artist(enriched)

    return {
        "artist": enriched,
        "artist_name": artist_name,
        "theaudiodb_artist_id": theaudiodb_id,
        "musicbrainz_mbid": mbid,
        "source": "theaudiodb+musicbrainz",
        "theaudiodb_raw_s3_key": theaudiodb_raw_key,
        "musicbrainz_raw_s3_key": musicbrainz_raw_key,
        "processed_s3_key": processed_key,
    }

"""Cliente Last.fm para descoberta e metadados de artistas."""

import os
from typing import Any

import requests
from src.utils.telemetry import increment

BASE_URL = "https://ws.audioscrobbler.com/2.0/"
DEFAULT_TIMEOUT_SECONDS = 10


class LastFMError(Exception):
    """Erro esperado durante uma consulta ao Last.fm."""


class ArtistNotFoundError(LastFMError):
    """O Last.fm não encontrou o artista solicitado."""


def _get(params: dict[str, str]) -> dict[str, Any]:
    api_key = os.getenv("LASTFM_API_KEY")
    if not api_key:
        raise LastFMError("A variável de ambiente LASTFM_API_KEY não está configurada.")
    payload = {**params, "api_key": api_key, "format": "json"}
    increment("lastfm.requests")
    try:
        response = requests.get(BASE_URL, params=payload, timeout=DEFAULT_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.Timeout as error:
        raise LastFMError("A requisição ao Last.fm excedeu o tempo limite.") from error
    except requests.RequestException as error:
        raise LastFMError(f"Erro HTTP ao consultar o Last.fm: {error}") from error
    try:
        data = response.json()
    except (requests.exceptions.JSONDecodeError, ValueError) as error:
        raise LastFMError("O Last.fm retornou uma resposta JSON inválida.") from error
    if not isinstance(data, dict):
        raise LastFMError("O Last.fm retornou uma estrutura JSON inesperada.")
    if data.get("error"):
        if data.get("error") == 6:
            raise ArtistNotFoundError(data.get("message", "Artista não encontrado."))
        raise LastFMError(data.get("message", "Erro retornado pelo Last.fm."))
    return data


def search_artist(artist_name: str, limit: int = 10) -> dict[str, Any]:
    if not isinstance(artist_name, str) or not artist_name.strip():
        raise ValueError("O nome do artista não pode estar vazio.")
    data = _get({"method": "artist.search", "artist": artist_name.strip(), "limit": str(limit)})
    artists = data.get("results", {}).get("artistmatches", {}).get("artist")
    if not isinstance(artists, list) or not artists:
        raise ArtistNotFoundError(f'Artista "{artist_name.strip()}" não encontrado.')
    return data


def get_artist_info(artist_name: str) -> dict[str, Any]:
    if not isinstance(artist_name, str) or not artist_name.strip():
        raise ValueError("O nome do artista não pode estar vazio.")
    data = _get({"method": "artist.getInfo", "artist": artist_name.strip(), "autocorrect": "1"})
    artist = data.get("artist")
    if not isinstance(artist, dict) or not isinstance(artist.get("name"), str):
        raise ArtistNotFoundError(f'Artista "{artist_name.strip()}" não encontrado.')
    return data

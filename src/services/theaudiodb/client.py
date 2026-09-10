"""Cliente HTTP simples para extrair dados de artistas do TheAudioDB."""

import os
from typing import Any

import requests


BASE_URL = "https://www.theaudiodb.com/api/v1/json"
DEFAULT_TIMEOUT_SECONDS = 10


class TheAudioDBError(Exception):
    """Erro esperado durante uma consulta ao TheAudioDB."""


class ArtistNotFoundError(TheAudioDBError):
    """O TheAudioDB não encontrou o artista solicitado."""


def search_artist(artist_name: str) -> dict[str, Any]:
    """Pesquisa um artista e devolve o JSON original do TheAudioDB.

    A função somente valida a integração e retorna a resposta recebida. Nenhuma
    transformação para o modelo interno do SoundScope é realizada nesta etapa.

    Raises:
        ValueError: Se o nome do artista estiver vazio.
        TheAudioDBError: Se faltar configuração ou a comunicação/resposta falhar.
        ArtistNotFoundError: Se a API não retornar nenhum artista.
    """
    if not isinstance(artist_name, str) or not artist_name.strip():
        raise ValueError("O nome do artista não pode estar vazio.")

    api_key = os.getenv("THEAUDIODB_API_KEY")
    if not api_key:
        raise TheAudioDBError(
            "A variável de ambiente THEAUDIODB_API_KEY não está configurada."
        )

    url = f"{BASE_URL}/{api_key}/search.php"

    try:
        response = requests.get(
            url,
            params={"s": artist_name.strip()},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.Timeout as error:
        raise TheAudioDBError("A requisição ao TheAudioDB excedeu o tempo limite.") from error
    except requests.RequestException as error:
        raise TheAudioDBError(f"Erro HTTP ao consultar o TheAudioDB: {error}") from error

    try:
        data = response.json()
    except (requests.exceptions.JSONDecodeError, ValueError) as error:
        raise TheAudioDBError("O TheAudioDB retornou uma resposta JSON inválida.") from error

    if not isinstance(data, dict) or "artists" not in data:
        raise TheAudioDBError("O TheAudioDB retornou uma estrutura JSON inesperada.")

    if not data["artists"]:
        raise ArtistNotFoundError(f'Artista "{artist_name.strip()}" não encontrado.')

    return data

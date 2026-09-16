"""Cliente HTTP simples para extrair dados RAW do MusicBrainz."""

import os
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from math import isfinite
from typing import Any

import requests

BASE_URL = "https://musicbrainz.org/ws/2"
DEFAULT_TIMEOUT_SECONDS = 10
MIN_REQUEST_INTERVAL_SECONDS = 1.0
MAX_REQUEST_ATTEMPTS = 3
MAX_RETRY_DELAY_SECONDS = 60.0
TRANSIENT_HTTP_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
DEFAULT_USER_AGENT = "SoundScope/1.0 (https://github.com/zampieri05/soundscope)"

_rate_limit_lock = threading.Lock()
_last_request_started_at = 0.0


class MusicBrainzError(Exception):
    """Erro esperado durante uma consulta ao MusicBrainz."""


class ArtistNotFoundError(MusicBrainzError):
    """O MusicBrainz não encontrou o artista solicitado."""


def _wait_for_rate_limit() -> None:
    """Mantém no máximo uma requisição por segundo neste processo."""
    global _last_request_started_at

    with _rate_limit_lock:
        elapsed = time.monotonic() - _last_request_started_at
        if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
            time.sleep(MIN_REQUEST_INTERVAL_SECONDS - elapsed)
        _last_request_started_at = time.monotonic()


def _retry_delay(response: requests.Response, retry_number: int) -> float:
    """Calcula a espera indicada pelo servidor ou o backoff exponencial."""
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            delay = float(retry_after)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                delay = (retry_at - datetime.now(timezone.utc)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                delay = -1
        if isfinite(delay) and delay >= 0:
            return min(delay, MAX_RETRY_DELAY_SECONDS)

    return float(2 ** (retry_number - 1))


def _get_json(url: str, params: dict[str, str]) -> dict[str, Any]:
    """Executa uma requisição identificada e devolve seu documento JSON."""
    user_agent = os.getenv("MUSICBRAINZ_USER_AGENT", DEFAULT_USER_AGENT).strip()
    if not user_agent:
        raise MusicBrainzError("O User-Agent do MusicBrainz não pode estar vazio.")

    response: requests.Response | None = None
    for attempt in range(1, MAX_REQUEST_ATTEMPTS + 1):
        _wait_for_rate_limit()
        response = None
        try:
            response = requests.get(
                url,
                params=params,
                headers={"User-Agent": user_agent, "Accept": "application/json"},
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            break
        except requests.Timeout as error:
            raise MusicBrainzError(
                "A requisição ao MusicBrainz excedeu o tempo limite."
            ) from error
        except requests.HTTPError as error:
            error_response = error.response if error.response is not None else response
            status_code = getattr(error_response, "status_code", None)
            if (
                status_code in TRANSIENT_HTTP_STATUS_CODES
                and attempt < MAX_REQUEST_ATTEMPTS
            ):
                time.sleep(_retry_delay(error_response, attempt))
                continue
            raise MusicBrainzError(
                f"Erro HTTP ao consultar o MusicBrainz: {error}"
            ) from error
        except requests.RequestException as error:
            raise MusicBrainzError(
                f"Erro HTTP ao consultar o MusicBrainz: {error}"
            ) from error

    if (
        response is None
    ):  # pragma: no cover - o loop só termina após uma resposta válida
        raise MusicBrainzError("O MusicBrainz não retornou uma resposta.")

    try:
        data = response.json()
    except (requests.exceptions.JSONDecodeError, ValueError) as error:
        raise MusicBrainzError(
            "O MusicBrainz retornou uma resposta JSON inválida."
        ) from error

    if not isinstance(data, dict):
        raise MusicBrainzError("O MusicBrainz retornou uma estrutura JSON inesperada.")
    return data


def search_artist(artist_name: str) -> dict[str, Any]:
    """Pesquisa um artista e devolve o JSON original do MusicBrainz."""
    if not isinstance(artist_name, str) or not artist_name.strip():
        raise ValueError("O nome do artista não pode estar vazio.")

    name = artist_name.strip()
    data = _get_json(
        f"{BASE_URL}/artist/",
        params={"query": name, "fmt": "json"},
    )

    if "artists" not in data or not isinstance(data["artists"], list):
        raise MusicBrainzError("O MusicBrainz retornou uma estrutura JSON inesperada.")
    if not data["artists"]:
        raise ArtistNotFoundError(f'Artista "{name}" não encontrado.')
    return data


def get_artist_details(mbid: str) -> dict[str, Any]:
    """Consulta um artista por MBID e devolve o JSON original."""
    if not isinstance(mbid, str) or not mbid.strip():
        raise ValueError("O MBID do artista não pode estar vazio.")

    artist_mbid = mbid.strip()
    data = _get_json(
        f"{BASE_URL}/artist/{artist_mbid}",
        params={
            "inc": "aliases+genres+tags+artist-rels",
            "fmt": "json",
        },
    )

    if not isinstance(data.get("id"), str) or not isinstance(data.get("name"), str):
        raise MusicBrainzError("O MusicBrainz retornou uma estrutura JSON inesperada.")
    return data


def get_release_groups(mbid: str) -> dict[str, Any]:
    """Lista grupos de lançamentos do artista em uma única requisição."""
    if not isinstance(mbid, str) or not mbid.strip():
        raise ValueError("O MBID do artista não pode estar vazio.")
    data = _get_json(
        f"{BASE_URL}/release-group/",
        params={"artist": mbid.strip(), "type": "album", "limit": "100", "fmt": "json"},
    )
    if not isinstance(data.get("release-groups"), list):
        raise MusicBrainzError("O MusicBrainz retornou uma estrutura JSON inesperada.")
    return data

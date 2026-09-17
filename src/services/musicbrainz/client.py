"""Cliente HTTP simples para extrair dados RAW do MusicBrainz."""

import os
import logging
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
MAX_RETRY_DELAY_SECONDS = 5.0
RELEASE_GROUP_PAGE_SIZE = 100
MAX_RELEASE_GROUP_PAGES = 20
TRANSIENT_HTTP_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
DEFAULT_USER_AGENT = "SoundScope/1.0 (https://github.com/zampieri05/soundscope)"

_rate_limit_lock = threading.Lock()
_last_request_started_at = 0.0
logger = logging.getLogger(__name__)


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


def _get_json(
    url: str, params: dict[str, str], *, operation: str, subject: str
) -> dict[str, Any]:
    """Executa uma requisição identificada e devolve seu documento JSON."""
    user_agent = os.getenv("MUSICBRAINZ_USER_AGENT", DEFAULT_USER_AGENT).strip()
    if not user_agent:
        raise MusicBrainzError("O User-Agent do MusicBrainz não pode estar vazio.")

    response: requests.Response | None = None
    for attempt in range(1, MAX_REQUEST_ATTEMPTS + 1):
        _wait_for_rate_limit()
        logger.info(
            "MusicBrainz request operation=%s subject=%s attempt=%d/%d",
            operation, subject, attempt, MAX_REQUEST_ATTEMPTS,
        )
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
            if attempt < MAX_REQUEST_ATTEMPTS:
                delay = min(float(2 ** (attempt - 1)), MAX_RETRY_DELAY_SECONDS)
                logger.warning(
                    "MusicBrainz timeout; retrying operation=%s subject=%s "
                    "attempt=%d/%d delay=%.1fs error_type=%s",
                    operation, subject, attempt, MAX_REQUEST_ATTEMPTS, delay,
                    type(error).__name__,
                )
                time.sleep(delay)
                continue
            logger.error(
                "MusicBrainz timeout exhausted operation=%s subject=%s attempts=%d "
                "error_type=%s",
                operation, subject, MAX_REQUEST_ATTEMPTS, type(error).__name__,
            )
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
                delay = _retry_delay(error_response, attempt)
                logger.warning(
                    "MusicBrainz transient HTTP status; retrying operation=%s "
                    "subject=%s status=%s attempt=%d/%d delay=%.1fs",
                    operation, subject, status_code, attempt,
                    MAX_REQUEST_ATTEMPTS, delay,
                )
                time.sleep(delay)
                continue
            logger.error(
                "MusicBrainz HTTP failure operation=%s subject=%s status=%s "
                "attempt=%d/%d transient=%s",
                operation, subject, status_code, attempt, MAX_REQUEST_ATTEMPTS,
                status_code in TRANSIENT_HTTP_STATUS_CODES,
            )
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
        operation="artist_search",
        subject=name,
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
        operation="artist_details",
        subject=artist_mbid,
    )

    if not isinstance(data.get("id"), str) or not isinstance(data.get("name"), str):
        raise MusicBrainzError("O MusicBrainz retornou uma estrutura JSON inesperada.")
    return data


def get_release_groups(mbid: str) -> dict[str, Any]:
    """Lista release groups com paginação por ``offset`` e teto defensivo.

    O retorno agregado mantém o contrato de uma única resposta para callers.
    IDs repetidos entre páginas são eliminados e uma página vazia interrompe a
    coleta, evitando loops diante de contagens inconsistentes.
    """
    if not isinstance(mbid, str) or not mbid.strip():
        raise ValueError("O MBID do artista não pode estar vazio.")
    artist_mbid = mbid.strip()
    groups: list[Any] = []
    seen_ids: set[str] = set()
    total: int | None = None
    offset = 0
    pages = 0
    while pages < MAX_RELEASE_GROUP_PAGES:
        data = _get_json(
            f"{BASE_URL}/release-group/",
            params={"artist": artist_mbid, "limit": str(RELEASE_GROUP_PAGE_SIZE),
                    "offset": str(offset), "fmt": "json"},
            operation="release_groups",
            subject=artist_mbid,
        )
        page = data.get("release-groups")
        if not isinstance(page, list):
            raise MusicBrainzError("O MusicBrainz retornou uma estrutura JSON inesperada.")
        count = data.get("release-group-count")
        if total is None and isinstance(count, int) and count >= 0:
            total = count
        if not page:
            break
        for group in page:
            group_id = group.get("id") if isinstance(group, dict) else None
            if isinstance(group_id, str):
                if group_id in seen_ids:
                    continue
                seen_ids.add(group_id)
            groups.append(group)
        pages += 1
        offset += len(page)
        if (total is not None and offset >= total) or len(page) < RELEASE_GROUP_PAGE_SIZE:
            break
    return {"release-group-count": total if total is not None else len(groups),
            "release-group-offset": 0, "release-groups": groups, "pages-fetched": pages}

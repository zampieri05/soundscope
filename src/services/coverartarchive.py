"""Cliente resiliente e limitado do Cover Art Archive."""

import logging
import os
from typing import Any

import requests

BASE_URL = "https://coverartarchive.org/release-group"
DEFAULT_TIMEOUT_SECONDS = 2.5
USER_AGENT = os.getenv("MUSICBRAINZ_USER_AGENT", "SoundScope/1.0 (https://github.com/zampieri05/soundscope)")
logger = logging.getLogger(__name__)


def front_cover_url(release_group_mbid: str) -> str | None:
    """Retorna somente uma imagem explicitamente marcada como frontal."""
    try:
        response = requests.get(
            f"{BASE_URL}/{release_group_mbid}",
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload: Any = response.json()
        images = payload.get("images") if isinstance(payload, dict) else None
        for image in images if isinstance(images, list) else []:
            if isinstance(image, dict) and image.get("front") is True:
                thumbnails = image.get("thumbnails")
                if isinstance(thumbnails, dict):
                    url = thumbnails.get("500") or thumbnails.get("large")
                    if isinstance(url, str) and url.strip():
                        return url.strip()
                url = image.get("image")
                if isinstance(url, str) and url.strip():
                    return url.strip()
    except (requests.RequestException, ValueError, TypeError):
        logger.info("Cover Art Archive unavailable release_group=%s", release_group_mbid)
    return None

"""Orquestração resiliente multi-source de artistas enriquecidos."""

from dataclasses import asdict
import logging
from typing import Any, TypedDict
import unicodedata
import uuid

from src.models import EnrichedArtist, NormalizedArtist
from src.pipeline.enrichment.artist import enrich_artist, partial_artist, _comparable_name
from src.pipeline.ingestion.errors import UsableArtistNotFoundError
from src.pipeline.ingestion.theaudiodb import _first_artist_id
from src.pipeline.transformers import (
    transform_musicbrainz_albums, transform_musicbrainz_artist,
    transform_musicbrainz_members, transform_theaudiodb_albums,
    transform_theaudiodb_artist,
)
from src.services.musicbrainz import client as musicbrainz_client
from src.services.musicbrainz.client import MusicBrainzError, ArtistNotFoundError
from src.services.theaudiodb import client as theaudiodb_client
from src.services.theaudiodb.client import TheAudioDBError, AlbumsNotFoundError
from src.storage.dynamodb import save_enriched_artist
from src.storage.s3 import save_processed_json, save_raw_json
from src.utils.telemetry import increment, measure
from src.services.artist_resolver import query_variants, names_compatible


logger = logging.getLogger(__name__)


class EnrichedArtistProcessingResult(TypedDict, total=False):
    artist: EnrichedArtist
    artist_name: str
    theaudiodb_artist_id: str | None
    musicbrainz_mbid: str | None
    source: str
    sources: dict[str, bool]
    theaudiodb_raw_s3_key: str | None
    musicbrainz_raw_s3_key: str | None
    processed_s3_key: str


def _candidate_names(candidate: dict[str, Any]) -> set[str]:
    names = {_comparable_name(candidate.get("name", ""))}
    aliases = candidate.get("aliases")
    if isinstance(aliases, list):
        for alias in aliases:
            value = alias.get("name") if isinstance(alias, dict) else alias
            if isinstance(value, str):
                names.add(_comparable_name(value))
    return names - {""}


def _select_musicbrainz_artist(search_raw: Any, query: str) -> dict[str, Any]:
    """Escolhe correspondência exata pelo nome/alias e usa o score oficial.

    Não há score SoundScope: candidatos sem nome/alias exatamente equivalente
    (normalização Unicode) ou com score oficial abaixo de 80 são rejeitados.
    Empates perfeitos são considerados homônimos ambíguos, salvo se apenas um
    candidato trouxer disambiguation, país ou tipo para torná-lo mais específico.
    """
    artists = search_raw.get("artists") if isinstance(search_raw, dict) else None
    wanted = _comparable_name(query)
    eligible: list[dict[str, Any]] = []
    if isinstance(artists, list):
        for candidate in artists:
            if not isinstance(candidate, dict):
                continue
            if wanted not in _candidate_names(candidate):
                logger.info(
                    "MusicBrainz candidate rejected reason=name_mismatch "
                    "candidate_mbid=%r",
                    candidate.get("id"),
                )
                continue
            score = candidate.get("score")
            if score is not None and (not isinstance(score, int) or score < 80):
                logger.info(
                    "MusicBrainz candidate rejected reason=score_too_low "
                    "candidate_mbid=%r score=%r",
                    candidate.get("id"), score,
                )
                continue
            if isinstance(candidate.get("id"), str) and candidate["id"].strip():
                eligible.append(candidate)
    if not eligible:
        raise ArtistNotFoundError(
            "A busca do MusicBrainz não retornou correspondência confiável."
        )
    eligible.sort(key=lambda item: (
        -(item.get("score") if isinstance(item.get("score"), int) else 0),
        0 if _comparable_name(item.get("name", "")) == wanted else 1,
        -sum(bool(item.get(key)) for key in ("type", "country", "disambiguation")),
        item["id"],
    ))
    if len(eligible) > 1:
        def rank(item: dict[str, Any]) -> tuple[int, int, int]:
            return (item.get("score") if isinstance(item.get("score"), int) else 0,
                    int(_comparable_name(item.get("name", "")) == wanted),
                    sum(bool(item.get(key)) for key in ("type", "country", "disambiguation")))
        if rank(eligible[0]) == rank(eligible[1]):
            raise ArtistNotFoundError(
                "A busca do MusicBrainz retornou homônimos ambíguos."
            )
    return eligible[0]


# Compatibilidade para callers/testes antigos; novas chamadas devem informar a consulta.
def _first_musicbrainz_artist(search_raw: Any) -> dict[str, Any]:
    artists = search_raw.get("artists") if isinstance(search_raw, dict) else None
    if isinstance(artists, list):
        for item in artists:
            if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"].strip():
                return _select_musicbrainz_artist(search_raw, item["name"])
    raise ArtistNotFoundError("A busca não retornou artista utilizável.")


def _musicbrainz_id(artist: dict[str, Any]) -> str:
    return artist["id"].strip()


_COUNTRY_ALIASES = {
    "br": "BR", "brazil": "BR", "brasil": "BR",
    "ca": "CA", "canada": "CA",
    "de": "DE", "germany": "DE", "deutschland": "DE",
    "fr": "FR", "france": "FR",
    "gb": "GB", "uk": "GB", "united kingdom": "GB", "great britain": "GB",
    "ie": "IE", "ireland": "IE",
    "is": "IS", "iceland": "IS",
    "mx": "MX", "mexico": "MX",
    "pt": "PT", "portugal": "PT",
    "us": "US", "usa": "US", "united states": "US",
    "united states of america": "US",
}


def _valid_mbid(value: Any) -> str | None:
    """Retorna a forma canônica apenas para um UUID MusicBrainz válido."""
    if not isinstance(value, str):
        return None
    try:
        parsed = uuid.UUID(value.strip())
    except (ValueError, AttributeError):
        return None
    return str(parsed)


def _country_identity(country: str | None, country_code: str | None) -> str | None:
    """Normaliza códigos/nomes explícitos, sem correspondência por substring."""
    for value in (country_code, country):
        if not isinstance(value, str) or not value.strip():
            continue
        normalized = unicodedata.normalize("NFKC", value).strip().casefold()
        if normalized in _COUNTRY_ALIASES:
            return _COUNTRY_ALIASES[normalized]
        # Campos editoriais do TheAudioDB podem terminar em um país explícito,
        # por exemplo "California, USA". Só o componente completo após a
        # última vírgula é considerado; não há busca genérica por substring.
        suffix = normalized.rsplit(",", 1)[-1].strip()
        if suffix in _COUNTRY_ALIASES:
            return _COUNTRY_ALIASES[suffix]
        if len(normalized) == 2 and normalized.isalpha():
            return normalized.upper()
        return normalized
    return None


def _identity_rejected(reason: str, tadb: NormalizedArtist,
                       mb: NormalizedArtist, score: Any) -> bool:
    logger.info(
        "Artist identity rejected reason=%s theaudiodb_artist_id=%s "
        "musicbrainz_mbid=%s score=%r",
        reason, tadb.source_artist_id, mb.source_artist_id, score,
    )
    return False


def _same_identity(tadb: NormalizedArtist, mb: NormalizedArtist,
                   search_match: dict[str, Any], details: dict[str, Any]) -> bool:
    names = _candidate_names(search_match) | _candidate_names(details)
    if (_comparable_name(tadb.name) not in names
            and not any(names_compatible(tadb.name, name) for name in names)):
        return _identity_rejected("name_mismatch", tadb, mb, search_match.get("score"))

    score = search_match.get("score")
    if score is not None and (not isinstance(score, int) or score < 80):
        return _identity_rejected("score_too_low", tadb, mb, score)

    tadb_mbid = _valid_mbid(tadb.musicbrainz_id)
    mb_mbid = _valid_mbid(mb.musicbrainz_id or details.get("id"))
    if tadb_mbid and mb_mbid:
        if tadb_mbid != mb_mbid:
            return _identity_rejected("mbid_mismatch", tadb, mb, score)
        # Um UUID compartilhado identifica deterministicamente a entidade; não
        # rejeitamos por divergências editoriais de localização entre fontes.
        return True

    left = _country_identity(tadb.country, tadb.country_code)
    right = _country_identity(mb.country, mb.country_code)
    if left and right and left != right:
        return _identity_rejected("country_mismatch", tadb, mb, score)
    return True


def process_enriched_artist(artist_name: str) -> EnrichedArtistProcessingResult:
    """Consulta as fontes independentemente e retorna a melhor visão utilizável."""
    tadb_artist = mb_artist = None
    tadb_id = mbid = None
    tadb_key = mb_key = None
    tadb_albums: list[Any] = []
    mb_albums: list[Any] = []
    members: list[Any] = []
    mb_match: dict[str, Any] = {}
    mb_details: dict[str, Any] = {}
    failures: list[Exception] = []
    extended_catalog = isinstance(getattr(theaudiodb_client, "AlbumsNotFoundError", None), type)

    try:
        raw = None
        tadb_query = artist_name
        last_tadb_not_found = None
        with measure("theaudiodb.artist_ms"):
            for candidate_query in query_variants(artist_name):
                try:
                    candidate_raw = theaudiodb_client.search_artist(candidate_query)
                    candidate_artist = transform_theaudiodb_artist(candidate_raw)
                    if names_compatible(artist_name, candidate_artist.name):
                        raw = candidate_raw
                        tadb_query = candidate_query
                        break
                except theaudiodb_client.ArtistNotFoundError as error:
                    last_tadb_not_found = error
        if raw is None:
            if last_tadb_not_found:
                raise last_tadb_not_found
            raise theaudiodb_client.ArtistNotFoundError(
                f'Artista "{artist_name}" não encontrado.'
            )
        if tadb_query != artist_name:
            logger.info("Artist Resolver matched TheAudioDB query_variant=%r", tadb_query)
        tadb_id = _first_artist_id(raw)
        with measure("s3.raw_ms"):
            tadb_key = save_raw_json("theaudiodb", raw, "artists", tadb_id)
        increment("s3.raw_writes")
        with measure("theaudiodb.transform_artist_ms"), measure("transform_ms"):
            tadb_artist = transform_theaudiodb_artist(raw)
        try:
            if not extended_catalog:
                raise AlbumsNotFoundError("Catálogo indisponível neste caller legado.")
            with measure("theaudiodb.albums_ms"):
                albums_raw = theaudiodb_client.search_albums(tadb_id)
            with measure("s3.raw_ms"):
                save_raw_json("theaudiodb", albums_raw, "albums", tadb_id)
            increment("s3.raw_writes")
            with measure("theaudiodb.transform_albums_ms"), measure("transform_ms"):
                tadb_albums = transform_theaudiodb_albums(albums_raw)
        except AlbumsNotFoundError:
            pass
    except (TheAudioDBError, UsableArtistNotFoundError) as error:
        failures.append(error)
        logger.info(
            "TheAudioDB source unavailable outcome=%s",
            type(error).__name__,
        )

    try:
        search_raw = None
        mb_match = None
        mb_query = artist_name
        last_mb_not_found = None
        with measure("musicbrainz.search_ms"):
            for candidate_query in query_variants(artist_name):
                try:
                    candidate_raw = musicbrainz_client.search_artist(candidate_query)
                    candidate_match = _select_musicbrainz_artist(
                        candidate_raw, candidate_query
                    )
                    if names_compatible(artist_name, candidate_match.get("name", "")):
                        search_raw = candidate_raw
                        mb_match = candidate_match
                        mb_query = candidate_query
                        break
                except ArtistNotFoundError as error:
                    last_mb_not_found = error
        if search_raw is None or mb_match is None:
            if last_mb_not_found:
                raise last_mb_not_found
            raise ArtistNotFoundError(
                "O Artist Resolver não encontrou correspondência confiável."
            )
        if mb_query != artist_name:
            logger.info("Artist Resolver matched MusicBrainz query_variant=%r", mb_query)
        mbid = _musicbrainz_id(mb_match)
        with measure("s3.raw_ms"):
            save_raw_json("musicbrainz", search_raw, "artists", mbid)
        increment("s3.raw_writes")
        with measure("musicbrainz.artist_ms"):
            mb_details = musicbrainz_client.get_artist_details(mbid)
        with measure("s3.raw_ms"):
            mb_key = save_raw_json("musicbrainz", mb_details, "artists", mbid)
        increment("s3.raw_writes")
        with measure("transform_ms"):
            mb_artist = transform_musicbrainz_artist(mb_details)
            members = transform_musicbrainz_members(mb_details)
        if extended_catalog:
            try:
                with measure("musicbrainz.release_groups_ms"):
                    release_raw = musicbrainz_client.get_release_groups(mbid)
                with measure("s3.raw_ms"):
                    save_raw_json("musicbrainz", release_raw, "release-groups", mbid)
                increment("s3.raw_writes")
                with measure("transform_ms"):
                    mb_albums = transform_musicbrainz_albums(release_raw)
            except MusicBrainzError as error:
                # get_release_groups only returns a fully collected snapshot. If
                # any page fails, discard it rather than presenting a partial
                # MusicBrainz catalog as complete.
                logger.warning(
                    "MusicBrainz release groups unavailable; discarding catalog "
                    "mbid=%s error_type=%s",
                    mbid, type(error).__name__,
                )
    except MusicBrainzError as error:
        failures.append(error)
        logger.info(
            "MusicBrainz source unavailable; considering fallback "
            "mbid=%s outcome=%s",
            mbid, type(error).__name__,
        )

    with measure("identity_ms"):
        same_identity = bool(tadb_artist and mb_artist and
                             _same_identity(tadb_artist, mb_artist, mb_match, mb_details))
    with measure("enrichment_ms"):
        if same_identity:
            enriched = (enrich_artist(tadb_artist, mb_artist, tadb_albums, mb_albums, members)
                        if extended_catalog else enrich_artist(tadb_artist, mb_artist))
        elif mb_artist:
            if not tadb_artist:
                logger.info("Using MusicBrainz fallback mbid=%s", mbid)
            enriched = partial_artist(mb_artist, mb_albums, members)
        elif tadb_artist:
            logger.info("Using TheAudioDB fallback artist_id=%s", tadb_id)
            enriched = partial_artist(tadb_artist, tadb_albums)
        else:
            enriched = None
    if enriched is None:
        not_found_types = (theaudiodb_client.ArtistNotFoundError,
                           ArtistNotFoundError,
                           UsableArtistNotFoundError)
        upstream_failures = [
            error for error in failures if not isinstance(error, not_found_types)
        ]
        if upstream_failures:
            logger.error(
                "All artist sources unusable after upstream failure failure_types=%s",
                ",".join(type(error).__name__ for error in upstream_failures),
            )
            raise upstream_failures[-1]
        if failures:
            raise UsableArtistNotFoundError("Nenhuma fonte encontrou o artista.")
        raise UsableArtistNotFoundError("Artista ausente.")

    # Cover Art Archive enrichment is intentionally lazy. Artist search must
    # not wait for dozens of image downloads; visible album cards request their
    # private /cover endpoint after the artist payload is rendered.

    serialized = asdict(enriched)
    if not extended_catalog:
        serialized.pop("members", None)
        serialized.pop("albums", None)
    # IDs encontrados durante a busca não são necessariamente IDs aceitos no
    # perfil final: o candidato do TheAudioDB pode ter sido rejeitado por
    # ``_same_identity``.  Persistências devem seguir as fontes efetivamente
    # presentes no perfil, nunca apenas a existência de um candidato upstream.
    profile_tadb_id = enriched.source_ids.get("theaudiodb")
    profile_mb_id = enriched.source_ids.get("musicbrainz")
    has_tadb_id = isinstance(profile_tadb_id, str) and bool(profile_tadb_id.strip())
    has_mb_id = isinstance(profile_mb_id, str) and bool(profile_mb_id.strip())
    storage_id = profile_tadb_id if has_tadb_id else profile_mb_id
    with measure("s3.processed_ms"):
        processed_key = save_processed_json(
            serialized, "artists", storage_id, data_type="enriched"
        )
    increment("s3.processed_writes")
    # A tabela atual exige artist-id do TheAudioDB; não se força migração no hotfix.
    if has_tadb_id:
        with measure("dynamodb_ms"):
            save_enriched_artist(enriched)
        increment("dynamodb_writes")
    sources = {"theaudiodb": has_tadb_id, "musicbrainz": has_mb_id}
    return {"artist": enriched, "artist_name": artist_name,
            "theaudiodb_artist_id": profile_tadb_id if has_tadb_id else None,
            "musicbrainz_mbid": profile_mb_id if has_mb_id else None,
            "source": "+".join(key for key, used in sources.items() if used),
            "sources": sources, "theaudiodb_raw_s3_key": tadb_key,
            "musicbrainz_raw_s3_key": mb_key, "processed_s3_key": processed_key}

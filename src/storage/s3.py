"""Persistência de documentos JSON RAW e processados no Amazon S3."""

import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import boto3
from botocore.exceptions import BotoCoreError, ClientError

_ENTITY_TYPES_BY_SOURCE = {
    "theaudiodb": frozenset({"artists", "albums"}),
    "musicbrainz": frozenset({"artists", "release-groups"}),
    "lastfm": frozenset({"artists"}),
}


class S3StorageError(Exception):
    """Indica que um documento não pôde ser armazenado no S3."""


class S3ObjectNotFoundError(S3StorageError):
    """Indica que uma leitura apontou para uma chave S3 inexistente."""


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise S3StorageError(f"{field} deve ser um texto não vazio.")
    return value.strip()


def _raw_key(
    source: str,
    entity_type: str,
    entity_id: str,
    extracted_at: datetime,
) -> str:
    """Monta uma chave histórica sem permitir separadores vindos do ID."""
    timestamp = extracted_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe_id = quote(entity_id, safe="")
    return f"raw/{source}/{entity_type}/{safe_id}/{timestamp}.json"


def _processed_key(
    entity_type: str,
    entity_id: str,
    processed_at: datetime,
    data_type: str | None = None,
) -> str:
    """Monta a chave histórica da camada processada."""
    timestamp = processed_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe_id = quote(entity_id, safe="")
    prefix = f"processed/{data_type}" if data_type else "processed"
    return f"{prefix}/{entity_type}/{safe_id}/{timestamp}.json"


def _json_body(data: Any, layer: str) -> bytes:
    if not isinstance(data, (dict, list)):
        raise S3StorageError(
            f"O documento {layer} deve ser um objeto ou lista JSON."
        )
    try:
        return json.dumps(data, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise S3StorageError(
            f"O documento {layer} não é serializável como JSON."
        ) from exc


def _configured_bucket() -> str:
    bucket = os.getenv("SOUNDSCOPE_S3_BUCKET", "").strip()
    if not bucket:
        raise S3StorageError("SOUNDSCOPE_S3_BUCKET não está configurado.")
    return bucket


def _put_json(
    bucket: str,
    key: str,
    body: bytes,
    s3_client: Any | None,
    layer: str,
) -> None:
    try:
        client = s3_client or boto3.client("s3")
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
        )
    except (BotoCoreError, ClientError) as exc:
        raise S3StorageError(
            f"Falha ao salvar o {layer} em s3://{bucket}/{key}."
        ) from exc


def get_json(
    key: str,
    *,
    s3_client: Any | None = None,
) -> Any:
    """Lê e decodifica um objeto JSON privado do bucket configurado.

    A função não lista o bucket e não altera ACLs. Uma chave ausente é
    distinguida dos demais erros para que callers possam tratá-la como miss.
    """
    key = _required_text(key, "key")
    bucket = _configured_bucket()
    try:
        client = s3_client or boto3.client("s3")
        response = client.get_object(Bucket=bucket, Key=key)
        body = response["Body"].read()
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"NoSuchKey", "404", "NotFound"}:
            raise S3ObjectNotFoundError(
                f"Objeto S3 não encontrado em s3://{bucket}/{key}."
            ) from exc
        raise S3StorageError(
            f"Falha ao ler objeto JSON em s3://{bucket}/{key}."
        ) from exc
    except (BotoCoreError, KeyError, AttributeError, OSError) as exc:
        raise S3StorageError(
            f"Falha ao ler objeto JSON em s3://{bucket}/{key}."
        ) from exc
    try:
        return json.loads(body)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise S3StorageError(
            f"Objeto em s3://{bucket}/{key} não contém JSON válido."
        ) from exc


def put_json(
    key: str,
    data: Any,
    *,
    s3_client: Any | None = None,
) -> None:
    """Grava atomicamente um pequeno documento JSON em uma chave conhecida."""
    key = _required_text(key, "key")
    bucket = _configured_bucket()
    body = _json_body(data, "de índice")
    _put_json(bucket, key, body, s3_client, "índice de cache")


def save_raw_json(
    source: str,
    data: Any,
    entity_type: str,
    entity_id: str,
    *,
    s3_client: Any | None = None,
    extracted_at: datetime | None = None,
) -> str:
    """Serializa e salva um payload RAW, retornando a chave criada.

    O JSON enviado é o próprio documento recebido, sem envelope ou alteração de
    campos. Fonte, tipo, ID e instante UTC ficam registrados na chave do objeto.
    O cliente opcional e o instante opcional existem para manter testes unitários
    determinísticos; em produção, boto3 usa sua cadeia padrão de credenciais.
    """
    source = _required_text(source, "source").lower()
    if source not in _ENTITY_TYPES_BY_SOURCE:
        raise S3StorageError(f"source inválida: {source!r}.")

    entity_type = _required_text(entity_type, "entity_type").lower()
    if entity_type not in _ENTITY_TYPES_BY_SOURCE[source]:
        raise S3StorageError(
            f"entity_type inválido para {source}: {entity_type!r}."
        )
    entity_id = _required_text(entity_id, "entity_id")

    bucket = _configured_bucket()
    body = _json_body(data, "RAW")

    moment = extracted_at or datetime.now(timezone.utc)
    if not isinstance(moment, datetime) or moment.tzinfo is None:
        raise S3StorageError("extracted_at deve ser um datetime com fuso horário.")
    key = _raw_key(source, entity_type, entity_id, moment)

    _put_json(bucket, key, body, s3_client, "RAW")

    return key


def save_processed_json(
    data: Any,
    entity_type: str,
    entity_id: str,
    *,
    data_type: str | None = None,
    s3_client: Any | None = None,
    processed_at: datetime | None = None,
) -> str:
    """Serializa um modelo preparado para consumo na camada ``processed/``.

    Por padrão, a chave segue
    ``processed/<entity_type>/<entity_id>/<timestamp>.json`` para preservar a
    API da Fase 9. ``data_type='enriched'`` separa documentos enriquecidos em
    ``processed/enriched/``.
    O chamador deve fornecer um documento JSON explícito, e não uma dataclass ou
    outro objeto cuja serialização implícita possa esconder mudanças de esquema.
    """
    entity_type = _required_text(entity_type, "entity_type").lower()
    if entity_type != "artists":
        raise S3StorageError(f"entity_type processado inválido: {entity_type!r}.")
    entity_id = _required_text(entity_id, "entity_id")
    if data_type is not None:
        data_type = _required_text(data_type, "data_type").lower()
        if data_type != "enriched":
            raise S3StorageError(f"data_type processado inválido: {data_type!r}.")
    bucket = _configured_bucket()
    body = _json_body(data, "processado")

    moment = processed_at or datetime.now(timezone.utc)
    if not isinstance(moment, datetime) or moment.tzinfo is None:
        raise S3StorageError("processed_at deve ser um datetime com fuso horário.")
    key = _processed_key(entity_type, entity_id, moment, data_type)
    _put_json(bucket, key, body, s3_client, "documento processado")
    return key

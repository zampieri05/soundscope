"""Persistência de documentos RAW no Amazon S3."""

import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import boto3
from botocore.exceptions import BotoCoreError, ClientError

_ENTITY_TYPES_BY_SOURCE = {
    "theaudiodb": frozenset({"artists", "albums"}),
    "musicbrainz": frozenset({"artists"}),
}


class S3StorageError(Exception):
    """Indica que um documento RAW não pôde ser armazenado no S3."""


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

    bucket = os.getenv("SOUNDSCOPE_S3_BUCKET", "").strip()
    if not bucket:
        raise S3StorageError("SOUNDSCOPE_S3_BUCKET não está configurado.")
    if not isinstance(data, (dict, list)):
        raise S3StorageError("O documento RAW deve ser um objeto ou lista JSON.")

    try:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise S3StorageError("O documento RAW não é serializável como JSON.") from exc

    moment = extracted_at or datetime.now(timezone.utc)
    if not isinstance(moment, datetime) or moment.tzinfo is None:
        raise S3StorageError("extracted_at deve ser um datetime com fuso horário.")
    key = _raw_key(source, entity_type, entity_id, moment)

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
            f"Falha ao salvar o RAW em s3://{bucket}/{key}."
        ) from exc

    return key

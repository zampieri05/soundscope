"""Persistência da visão enriquecida de artistas no Amazon DynamoDB."""

import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from src.models import EnrichedArtist


class DynamoDBStorageError(Exception):
    """Indica que um artista enriquecido não pôde ser persistido."""


def _configured_table() -> str:
    table_name = os.getenv("SOUNDSCOPE_DYNAMODB_TABLE", "").strip()
    if not table_name:
        raise DynamoDBStorageError(
            "SOUNDSCOPE_DYNAMODB_TABLE não está configurado."
        )
    return table_name


def save_enriched_artist(
    artist: EnrichedArtist,
    *,
    dynamodb_resource: Any | None = None,
    updated_at: datetime | None = None,
) -> None:
    """Grava um ``EnrichedArtist`` em uma tabela DynamoDB já existente.

    O recurso e o instante opcionais tornam testes determinísticos. Em
    produção, o boto3 usa normalmente sua cadeia padrão de credenciais e a
    configuração de região do ambiente.
    """
    if not isinstance(artist, EnrichedArtist):
        raise DynamoDBStorageError("artist deve ser um EnrichedArtist.")

    artist_id = artist.source_ids.get("theaudiodb")
    if not isinstance(artist_id, str) or not artist_id.strip():
        raise DynamoDBStorageError(
            "source_ids deve conter um ID do TheAudioDB não vazio."
        )

    moment = updated_at or datetime.now(timezone.utc)
    if not isinstance(moment, datetime) or moment.tzinfo is None:
        raise DynamoDBStorageError("updated_at deve ser um datetime com fuso horário.")

    # DynamoDB aceita mapas nativamente. Campos opcionais ausentes são
    # omitidos, evitando atributos NULL sem valor para consulta.
    item = {
        key: value
        for key, value in asdict(artist).items()
        if value is not None
    }
    item["source_ids"] = {
        source: source_id
        for source, source_id in item["source_ids"].items()
        if source_id is not None
    }
    item["artist-id"] = artist_id.strip()
    item["updated_at"] = moment.astimezone(timezone.utc).isoformat()

    table_name = _configured_table()
    try:
        resource = dynamodb_resource or boto3.resource("dynamodb")
        resource.Table(table_name).put_item(Item=item)
    except (BotoCoreError, ClientError) as exc:
        raise DynamoDBStorageError(
            f"Falha ao salvar o artista {artist_id!r} no DynamoDB."
        ) from exc

"""Camadas de persistência do SoundScope."""

from src.storage.dynamodb import DynamoDBStorageError, save_enriched_artist
from src.storage.s3 import S3StorageError, save_processed_json, save_raw_json

__all__ = [
    "DynamoDBStorageError",
    "S3StorageError",
    "save_enriched_artist",
    "save_processed_json",
    "save_raw_json",
]

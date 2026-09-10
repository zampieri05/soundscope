"""Camadas de persistência do SoundScope."""

from src.storage.s3 import S3StorageError, save_raw_json

__all__ = ["S3StorageError", "save_raw_json"]

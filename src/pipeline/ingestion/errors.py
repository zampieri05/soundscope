"""Erros esperados durante a orquestração de ingestão."""


class IngestionError(ValueError):
    """A resposta extraída não pode ser encaminhada para persistência."""


class InvalidIngestionResponseError(IngestionError):
    """O cliente retornou uma resposta com estrutura RAW inválida."""


class UsableArtistNotFoundError(IngestionError):
    """A resposta não contém um artista com identificador utilizável."""

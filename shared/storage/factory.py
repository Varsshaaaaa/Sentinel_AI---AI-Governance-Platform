"""Repository factory."""

from functools import lru_cache

from shared.config.settings import get_settings
from shared.storage.base import Repository
from shared.storage.memory import MemoryRepository


@lru_cache
def get_repository() -> Repository:
    settings = get_settings()
    if settings.storage_backend == "dynamodb":
        from shared.storage.dynamodb import DynamoDBRepository

        return DynamoDBRepository()
    return MemoryRepository()

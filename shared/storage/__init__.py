"""Storage repository interfaces and implementations."""

from shared.storage.base import Repository
from shared.storage.factory import get_repository

__all__ = ["Repository", "get_repository"]

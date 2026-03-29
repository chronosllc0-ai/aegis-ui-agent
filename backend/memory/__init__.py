"""Persistent memory system with vector-based semantic retrieval."""

from .embeddings import get_embedding
from .service import MemoryService

__all__ = ["MemoryService", "get_embedding"]

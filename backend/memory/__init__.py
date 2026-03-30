"""Persistent memory system with vector-based semantic retrieval."""

from .service import MemoryService
from .embeddings import get_embedding

__all__ = ["MemoryService", "get_embedding"]

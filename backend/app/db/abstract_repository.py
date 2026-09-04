from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any

class AbstractRepository(ABC):
    @abstractmethod
    async def create(self, collection: str, data: dict) -> dict:
        """Create a document in the specified collection."""
        pass
    
    @abstractmethod
    async def get(self, collection: str, doc_id: str) -> Optional[dict]:
        """Get a document by ID."""
        pass
    
    @abstractmethod
    async def query(
        self,
        collection: str,
        filters: Optional[List[tuple]] = None,
        order_by: Optional[List[tuple]] = None,
        limit: Optional[int] = None
    ) -> List[dict]:
        """Query documents with filters and ordering."""
        pass
    
    @abstractmethod
    async def update(self, collection: str, doc_id: str, data: dict) -> dict:
        """Update a document."""
        pass
    
    @abstractmethod
    async def delete(self, collection: str, doc_id: str) -> bool:
        """Delete a document."""
        pass

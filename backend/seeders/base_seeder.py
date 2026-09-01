import logging
from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class BaseSeeder(ABC):
    """Base class for all seeders."""
    
    def __init__(self, tenant_ids: Optional[List[str]] = None, dry_run: bool = False):
        self.tenant_ids = tenant_ids
        self.dry_run = dry_run
        self.created_count = 0
        self.skipped_count = 0
        self.errors = []
        self._init_logger()
    
    def _init_logger(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def seed(self) -> Dict[str, Any]:
        """Execute the seeding logic. Must be implemented by subclasses."""
        pass
    
    @abstractmethod
    def unseed(self) -> Dict[str, Any]:
        """Remove seeded data. Must be implemented by subclasses."""
        pass
    
    def log_info(self, message: str):
        self.logger.info(f"[{self.__class__.__name__}] {message}")
    
    def log_warning(self, message: str):
        self.logger.warning(f"[{self.__class__.__name__}] {message}")
    
    def log_error(self, message: str):
        self.logger.error(f"[{self.__class__.__name__}] {message}")
        self.errors.append(message)
    
    def get_summary(self) -> Dict[str, Any]:
        return {
            "seeder": self.__class__.__name__,
            "created": self.created_count,
            "skipped": self.skipped_count,
            "errors": len(self.errors),
            "dry_run": self.dry_run
        }
    
    def _is_demo_tenant(self, tenant_id: str) -> bool:
        """Check if a tenant is a demo tenant."""
        demo_tenants = ["fixedwing", "rotarywing", "demoairport", "demostate"]
        return tenant_id in demo_tenants
    
    def _get_tenant_ids(self) -> List[str]:
        """Get tenant IDs to seed. If self.tenant_ids is None, return all demo tenants."""
        if self.tenant_ids:
            return self.tenant_ids
        return ["fixedwing", "rotarywing", "demoairport", "demostate"]

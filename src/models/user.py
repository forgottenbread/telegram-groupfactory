from dataclasses import dataclass
from typing import Optional

@dataclass
class User:
    """Data class representing a Telegram user"""
    id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    access_hash: Optional[int] = None
    
    def __post_init__(self):
        if self.id is None:
            raise ValueError("User ID cannot be None")

    @property
    def name(self) -> str:
        parts = [part for part in [self.first_name, self.last_name] if part]
        return " ".join(parts) or self.username or str(self.id)
    
    @classmethod
    def from_dict(cls, data: dict):
        """Create User instance from dictionary"""
        return cls(
            id=data.get('id'),
            username=data.get('username'),
            first_name=data.get('first_name'),
            last_name=data.get('last_name'),
            access_hash=data.get('access_hash')
        )
    
    def to_dict(self):
        """Convert User instance to dictionary"""
        return {
            'id': self.id,
            'username': self.username,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'access_hash': self.access_hash
        }

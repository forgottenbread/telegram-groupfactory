import os
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from typing import Optional

API_KEY = os.environ.get("API_KEY", "default-api-key-change-in-production")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    """Verify API key from request header"""
    if api_key is None:
        raise HTTPException(
            status_code=403,
            detail="Missing API Key in X-API-Key header"
        )
    
    if api_key != API_KEY:
        raise HTTPException(
            status_code=403,
            detail="Invalid API Key"
        )
    
    return api_key

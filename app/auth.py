import hmac
import logging

from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

from app.config import settings

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key")


async def require_api_key(
    api_key: str = Security(_api_key_header),
) -> str:
    # Constant-time compare so response timing doesn't leak how much of the
    # key matched.
    if not hmac.compare_digest(api_key, settings.api_key):
        logger.warning("Unauthorized request — invalid API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return api_key

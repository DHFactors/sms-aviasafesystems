import os
import functools
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

import redis.asyncio as aioredis

from fastapi import HTTPException, Request
from loguru import logger

from app.core.config import settings
from app.firebase import get_db

redis_url = settings.REDIS_URL or os.getenv("REDIS_URL", "")
redis_enabled = settings.REDIS_ENABLED or os.getenv("REDIS_ENABLED", "").lower() == "true"

if not redis_url:
    logger.warning("REDIS_URL not set — rate limiting disabled. Set in Render dashboard or backend/.env")

_redis_client = None

async def get_redis():
    global _redis_client
    if not redis_enabled:
        return None
    if _redis_client is None:
        try:
            kwargs = dict(socket_connect_timeout=3)
            if not redis_url.startswith("rediss://"):
                from redis.asyncio.connection import SSLConnection
                kwargs["connection_class"] = SSLConnection
            kwargs["ssl_cert_reqs"] = "none"
            _redis_client = aioredis.from_url(redis_url, **kwargs)
            await _redis_client.ping()
            logger.info("Connected to Upstash Redis")
        except Exception as e:
            logger.warning(f"Redis unavailable, rate limiting disabled: {e}")
            _redis_client = None
    return _redis_client


RATE_LIMITS = {
    "vsr_submit":    (50,  86400),   # 50/day  (beta)
    "survey_submit": (settings.SURVEY_RATE_LIMIT, 86400),   # per-day, configurable (SURVEY_RATE_LIMIT)
    "mor_submit":    (20,  86400),   # 20/day  (beta)
    "dashboard":     (500, 3600),    # 500/hour (beta)
    "auth_attempts": (200, 3600),    # 200/hour (beta; safety net for shared login attempts)
    "register_tenant": (10, 3600),   # 10/hour per IP (self-service tenant registration)
    "join_team":     (30, 3600),     # 30/hour per IP (team-member onboarding)
    "register":      (10, 3600),     # 10/hour per IP (legacy /api/v1/auth/register)
    "copilot":       (120, 3600),    # 120/hour (beta; AI chat assistant per tenant)
}


def rate_limit(limit_type: str):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            request = _find_request(args, kwargs)
            if not request or not redis_enabled:
                return await func(*args, **kwargs)

            tenant_id = _get_tenant_id(kwargs)
            max_count, window_sec = _resolve_limit(limit_type, tenant_id)
            redis_key = _build_redis_key(limit_type, tenant_id, _get_client_ip(request), window_sec)

            try:
                r = await get_redis()
                if not r:
                    return await func(*args, **kwargs)

                count = await r.incr(redis_key)
                if count == 1:
                    await r.expire(redis_key, window_sec)

                ttl = await r.ttl(redis_key)
                remaining = max(0, max_count - count)

                resp_headers = {
                    "X-RateLimit-Limit": str(max_count),
                    "X-RateLimit-Remaining": str(remaining),
                    "X-RateLimit-Reset": str(int(_reset_epoch(window_sec))),
                }

                if count > max_count:
                    retry_after = max(1, int(ttl))
                    raise HTTPException(
                        status_code=429,
                        detail={
                            "success": False,
                            "error": "Rate limit exceeded",
                            "message": f"Max {max_count} requests per {_window_label(window_sec)}. Try again in {retry_after}s.",
                            "retry_after": retry_after,
                            "limit": max_count,
                            "remaining": 0,
                            "reset": _reset_iso(window_sec),
                        },
                        headers=resp_headers,
                    )

                # Attach rate limit info to request state for downstream use
                request.state.rate_limit = {
                    "limit": max_count,
                    "remaining": remaining,
                    "reset": _reset_iso(window_sec),
                }

            except HTTPException:
                raise
            except Exception as e:
                logger.warning(f"Rate limit check failed: {e}")

            return await func(*args, **kwargs)
        return wrapper
    return decorator


def _find_request(args, kwargs):
    for arg in args:
        if isinstance(arg, Request):
            return arg
    return kwargs.get("request")


def _get_tenant_id(kwargs: dict) -> str:
    user = kwargs.get("user") or kwargs.get("current_user")
    if user and isinstance(user, dict):
        return user.get("tenant_id")
    # Anonymous submissions (e.g. the public survey) carry the tenant in the
    # request body so the daily survey cap applies per tenant, not per IP.
    payload = kwargs.get("payload")
    if payload is not None:
        tid = getattr(payload, "tenantId", None) or getattr(payload, "tenant_id", None)
        if tid:
            return tid
    return None


def _resolve_limit(limit_type: str, tenant_id: Optional[str]) -> Tuple[int, int]:
    """Resolve the (max_count, window_sec) bucket for a limit type.

    Per-tenant survey overrides (tenants/{tid}/config.survey_rate_limit) take
    precedence over the global SURVEY_RATE_LIMIT setting for survey_submit.
    """
    base_count, window_sec = RATE_LIMITS.get(limit_type, (100, 3600))
    if limit_type == "survey_submit" and tenant_id:
        override = _tenant_survey_limit(tenant_id)
        if override:
            return override, window_sec
    return base_count, window_sec


def _tenant_survey_limit(tenant_id: str) -> Optional[int]:
    """Per-tenant daily survey cap from the tenant doc's `config` map.

    Returns None (-> global fallback) when the tenant has no explicit
    override, the value is not a positive int, or Firestore is unavailable.
    """
    try:
        snap = get_db().collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id).get()
        if snap.exists:
            config = (snap.to_dict() or {}).get("config") or {}
            val = config.get("survey_rate_limit")
            if isinstance(val, int) and val > 0:
                return val
    except Exception as e:
        logger.warning(f"Failed to resolve per-tenant survey limit for {tenant_id}: {e}")
    return None


def _build_redis_key(limit_type: str, tenant_id: Optional[str], ip: str, window_sec: int) -> str:
    """Build the Redis counter key for a rate-limited bucket.

    Survey submissions use the compact `rl:survey:{tenantId}:{date}` shape so
    operators can inspect per-tenant quota directly in Redis.
    """
    period_key = _period_key(window_sec)
    if limit_type == "survey_submit":
        bucket = tenant_id if tenant_id else f"ip:{ip}"
        return f"rl:survey:{bucket}:{period_key}"
    bucket_key = f"tenant:{tenant_id}" if tenant_id else f"ip:{ip}"
    return f"rl:{limit_type}:{bucket_key}:{period_key}"


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _period_key(window_sec: int) -> str:
    if window_sec >= 86400:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return datetime.now(timezone.utc).strftime("%Y-%m-%d:%H")


def _window_label(window_sec: int) -> str:
    if window_sec >= 86400:
        return "day"
    if window_sec >= 3600:
        return "hour"
    return f"{window_sec}s"


def _reset_epoch(window_sec: int) -> float:
    now = datetime.now(timezone.utc)
    if window_sec >= 86400:
        reset = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    else:
        reset = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return reset.timestamp()


def _reset_iso(window_sec: int) -> str:
    epoch = _reset_epoch(window_sec)
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()

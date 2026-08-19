import os
import time
import uuid
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
    "register_tenant": (5, 3600),    # 5/hour per IP (self-service tenant registration)
    "join_team":     (30, 3600),     # 30/hour per IP (team-member onboarding)
    "register":      (10, 3600),     # 10/hour per IP (legacy /api/v1/auth/register)
    "copilot":       (120, 3600),    # 120/hour (beta; AI chat assistant per tenant)
}

# Strict sliding-window limits enforced with Redis sorted sets (each request is
# logged with its timestamp and the window slides with real time, so a burst at
# the end of one hour can never leak into the next). These override the
# fixed-window buckets above for the same limit types.
#
#   login_failures: 5 failed login attempts / 15 minutes / IP
#   register_tenant: 5 registration attempts / hour / IP
#   verify_invite: 10 invite-verification attempts / hour / IP
SLIDING_WINDOW_LIMITS = {
    "login_failures": (5, 900),
    "register_tenant": (5, 3600),
    "verify_invite": (10, 3600),
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _sliding_key(limit_type: str, ip: str) -> str:
    return f"rl:sw:{limit_type}:ip:{ip}"


def _raise_429(
    limit_type: str,
    max_count: int,
    window_sec: int,
    retry_after: int,
    headers: Optional[dict] = None,
):
    """Raise a 429 with X-RateLimit-* headers and the required Retry-After."""
    headers = dict(headers or {})
    headers["Retry-After"] = str(retry_after)
    headers["X-RateLimit-Limit"] = str(max_count)
    headers["X-RateLimit-Remaining"] = "0"
    headers["X-RateLimit-Reset"] = str(int(_reset_epoch(window_sec)))
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
        headers=headers,
    )


async def sliding_window_count(limit_type: str, ip: str) -> int:
    """Return the number of events inside the current sliding window (no record)."""
    r = await get_redis()
    if not r:
        return 0
    max_count, window_sec = SLIDING_WINDOW_LIMITS.get(limit_type, (0, 3600))
    if max_count == 0:
        return 0
    key = _sliding_key(limit_type, ip)
    await r.zremrangebyscore(key, 0, _now_ms() - window_sec * 1000)
    return await r.zcard(key)


async def sliding_window_record(limit_type: str, ip: str, member: Optional[str] = None) -> int:
    """Record one event in the sliding-window log and return the new count."""
    r = await get_redis()
    if not r:
        return 0
    max_count, window_sec = SLIDING_WINDOW_LIMITS.get(limit_type, (0, 3600))
    if max_count == 0:
        return 0
    key = _sliding_key(limit_type, ip)
    now = _now_ms()
    member = member or f"{now}:{uuid.uuid4().hex}"
    await r.zadd(key, {member: now})
    await r.expire(key, window_sec)
    await r.zremrangebyscore(key, 0, now - window_sec * 1000)
    return await r.zcard(key)


async def sliding_window_oldest_epoch(limit_type: str, ip: str) -> Optional[float]:
    """Return the epoch (ms) of the oldest event in the window, or None."""
    r = await get_redis()
    if not r:
        return None
    rows = await r.zrange(_sliding_key(limit_type, ip), 0, 0, withscores=True)
    if not rows:
        return None
    return rows[0][1]


async def sliding_window_clear(limit_type: str, ip: str) -> None:
    """Drop the sliding-window counter for a limit+ip (e.g. after a successful login)."""
    r = await get_redis()
    if not r:
        return
    await r.delete(_sliding_key(limit_type, ip))


async def _retry_after_for(limit_type: str, ip: str, window_sec: int) -> int:
    """Seconds until the oldest event slides out of the window (min 1)."""
    oldest = await sliding_window_oldest_epoch(limit_type, ip)
    if not oldest:
        return 1
    return max(1, int((oldest / 1000 + window_sec) - _now_ms() / 1000))


async def enforce_login_rate_limit(request: Request) -> None:
    """Peek the login-failure sliding window for the caller's IP; 429 when blocked."""
    if not redis_enabled:
        return
    ip = _get_client_ip(request)
    count = await sliding_window_count("login_failures", ip)
    max_count, window_sec = SLIDING_WINDOW_LIMITS["login_failures"]
    if count >= max_count:
        _raise_429("login_failures", max_count, window_sec, await _retry_after_for("login_failures", ip, window_sec))


async def record_login_failure(request: Request) -> None:
    """Record a failed login for the caller's IP; 429 when the window is full."""
    if not redis_enabled:
        return
    ip = _get_client_ip(request)
    count = await sliding_window_record("login_failures", ip)
    max_count, window_sec = SLIDING_WINDOW_LIMITS["login_failures"]
    if count > max_count:
        _raise_429("login_failures", max_count, window_sec, await _retry_after_for("login_failures", ip, window_sec))


async def clear_login_failures(request: Request) -> None:
    """Reset the login-failure window after a successful login."""
    if not redis_enabled:
        return
    await sliding_window_clear("login_failures", _get_client_ip(request))


def _resolve_limit(limit_type: str, tenant_id: Optional[str]) -> Tuple[int, int]:
    """Resolve the (max_count, window_sec) bucket for a limit type.

    Sliding-window limit types resolve from SLIDING_WINDOW_LIMITS (strict per-IP
    auth/intake buckets). Per-tenant survey overrides
    (tenants/{tid}/config.survey_rate_limit) take precedence over the global
    SURVEY_RATE_LIMIT setting for survey_submit.
    """
    if limit_type in SLIDING_WINDOW_LIMITS:
        return SLIDING_WINDOW_LIMITS[limit_type]
    base_count, window_sec = RATE_LIMITS.get(limit_type, (100, 3600))
    if limit_type == "survey_submit" and tenant_id:
        override = _tenant_survey_limit(tenant_id)
        if override:
            return override, window_sec
    return base_count, window_sec


def rate_limit(limit_type: str):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            request = _find_request(args, kwargs)
            if not request or not redis_enabled:
                return await func(*args, **kwargs)

            tenant_id = _get_tenant_id(kwargs)
            ip = _get_client_ip(request)
            max_count, window_sec = _resolve_limit(limit_type, tenant_id)

            try:
                r = await get_redis()
                if not r:
                    return await func(*args, **kwargs)

                # Strict sliding-window limits (auth / intake) use a Redis
                # sorted set of timestamps instead of a fixed bucket.
                if limit_type in SLIDING_WINDOW_LIMITS:
                    count = await sliding_window_record(limit_type, ip)
                    remaining = max(0, max_count - count)
                    if count > max_count:
                        _raise_429(
                            limit_type,
                            max_count,
                            window_sec,
                            await _retry_after_for(limit_type, ip, window_sec),
                        )
                    request.state.rate_limit = {
                        "limit": max_count,
                        "remaining": remaining,
                        "reset": _reset_iso(window_sec),
                    }
                    return await func(*args, **kwargs)

                redis_key = _build_redis_key(limit_type, tenant_id, ip, window_sec)

                count = await r.incr(redis_key)
                if count == 1:
                    await r.expire(redis_key, window_sec)

                ttl = await r.ttl(redis_key)
                remaining = max(0, max_count - count)

                resp_headers = {
                    "Retry-After": str(max(1, int(ttl))),
                    "X-RateLimit-Limit": str(max_count),
                    "X-RateLimit-Remaining": str(remaining),
                    "X-RateLimit-Reset": str(int(_reset_epoch(window_sec))),
                }

                if count > max_count:
                    _raise_429(limit_type, max_count, window_sec, max(1, int(ttl)), resp_headers)

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

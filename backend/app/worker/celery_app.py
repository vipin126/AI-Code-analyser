"""Celery application factory.

Creates and configures the Celery instance with Redis as broker
and result backend. Tasks are auto-discovered from app.worker.tasks.
"""

import ssl

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "ai_code_analyzer",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# ── SSL config for cloud Redis (Upstash requires TLS) ────────
_is_ssl = settings.celery_broker_url.startswith("rediss://")

if _is_ssl:
    _ssl_opts = {"ssl_cert_reqs": ssl.CERT_NONE}
    celery_app.conf.broker_use_ssl = _ssl_opts
    celery_app.conf.redis_backend_use_ssl = _ssl_opts

# ── Celery Configuration ─────────────────────────────────────
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task behavior
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,

    # Startup connection retries (suppress Celery 6.0 warning)
    broker_connection_retry_on_startup=True,

    # Result expiration (24 hours)
    result_expires=86400,

    # Auto-discover tasks from this module
    include=["app.worker.tasks"],
)

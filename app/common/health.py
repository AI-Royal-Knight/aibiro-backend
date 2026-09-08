import os
import platform
import shutil
import time
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

import django
from django.conf import settings
from django.core.cache import cache
from django.db import connections


def check_database() -> Tuple[Dict[str, Any], bool]:
    """
    Check the status and responsiveness of all configured databases.
    Returns (result_dict, is_healthy).
    """
    db_results: Dict[str, Any] = {}
    all_healthy = True

    for db_alias in connections.databases:
        conn = connections[db_alias]
        start_time = time.perf_counter()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1;")
                cursor.fetchone()
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            db_results[db_alias] = {
                "status": "healthy",
                "vendor": conn.vendor,
                "latency_ms": latency_ms,
            }
        except Exception as exc:
            all_healthy = False
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            db_results[db_alias] = {
                "status": "unhealthy",
                "vendor": getattr(conn, "vendor", "unknown"),
                "latency_ms": latency_ms,
                "error": str(exc),
            }

    return db_results, all_healthy


def check_cache() -> Tuple[Dict[str, Any], bool]:
    """
    Check cache accessibility with a test key set/get/delete.
    Returns (result_dict, is_healthy).
    """
    start_time = time.perf_counter()
    test_key = "__healthcheck_probe__"
    try:
        cache.set(test_key, "ok", timeout=10)
        cached_val = cache.get(test_key)
        cache.delete(test_key)

        if cached_val != "ok":
            raise ValueError("Cache set/get value mismatch")

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "status": "healthy",
            "backend": cache.__class__.__module__ + "." + cache.__class__.__name__,
            "latency_ms": latency_ms,
        }, True
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "status": "unhealthy",
            "backend": cache.__class__.__module__ + "." + cache.__class__.__name__,
            "latency_ms": latency_ms,
            "error": str(exc),
        }, False


def check_storage() -> Tuple[Dict[str, Any], bool]:
    """
    Check available disk space and filesystem health.
    Returns (result_dict, is_healthy).
    """
    try:
        check_path = str(getattr(settings, "BASE_DIR", "."))
        usage = shutil.disk_usage(check_path)
        total_gb = round(usage.total / (1024**3), 2)
        used_gb = round(usage.used / (1024**3), 2)
        free_gb = round(usage.free / (1024**3), 2)
        used_percent = round((usage.used / usage.total) * 100, 1)

        # Warning threshold if less than 5% or 1GB free
        status = "healthy"
        if used_percent > 95 or free_gb < 1.0:
            status = "warning"

        return {
            "status": status,
            "free_gb": free_gb,
            "used_gb": used_gb,
            "total_gb": total_gb,
            "used_percent": used_percent,
        }, True
    except Exception as exc:
        return {
            "status": "unhealthy",
            "error": str(exc),
        }, False


def get_system_info() -> Dict[str, Any]:
    """
    Get system metadata.
    """
    return {
        "django_version": django.get_version(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "environment": os.environ.get("ENVIRONMENT", "dev"),
    }


def get_overall_health() -> Tuple[Dict[str, Any], bool]:
    """
    Aggregate all health checks.
    Returns (response_payload, is_overall_healthy).
    """
    db_results, db_healthy = check_database()
    cache_results, cache_healthy = check_cache()
    storage_results, storage_healthy = check_storage()
    system_info = get_system_info()

    # The service is considered healthy overall if the database is operational
    is_overall_healthy = db_healthy and cache_healthy

    status_str = "healthy" if is_overall_healthy else "unhealthy"

    payload = {
        "status": status_str,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": {
            "database": db_results,
            "cache": cache_results,
            "storage": storage_results,
        },
        "system": system_info,
    }

    return payload, is_overall_healthy

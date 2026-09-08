from datetime import datetime, timezone
from django.http import HttpRequest, JsonResponse
from django.views import View

from .health import check_database, get_overall_health


class HealthCheckView(View):
    """
    Comprehensive health check endpoint.
    Checks database, cache, storage, and system status.
    Returns 200 OK if healthy, 503 Service Unavailable if any critical service fails.
    """

    def get(self, request: HttpRequest) -> JsonResponse:
        payload, is_healthy = get_overall_health()
        status_code = 200 if is_healthy else 503
        return JsonResponse(payload, status=status_code)


class DatabaseHealthCheckView(View):
    """
    Dedicated database health check endpoint.
    Verifies connection and query execution for configured databases.
    Returns 200 OK if healthy, 503 Service Unavailable if database is unreachable.
    """

    def get(self, request: HttpRequest) -> JsonResponse:
        db_results, is_healthy = check_database()
        payload = {
            "status": "healthy" if is_healthy else "unhealthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "databases": db_results,
        }
        status_code = 200 if is_healthy else 503
        return JsonResponse(payload, status=status_code)


class LivenessHealthCheckView(View):
    """
    Lightweight liveness probe for load balancers and container orchestrators.
    Returns 200 OK when the process is running.
    """

    def get(self, request: HttpRequest) -> JsonResponse:
        payload = {
            "status": "alive",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return JsonResponse(payload, status=200)

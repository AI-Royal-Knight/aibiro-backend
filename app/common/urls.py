from django.urls import path
from .views import (
    HealthCheckView,
    DatabaseHealthCheckView,
    LivenessHealthCheckView,
)

urlpatterns = [
    path("", HealthCheckView.as_view(), name="health"),
    path("db/", DatabaseHealthCheckView.as_view(), name="health-db"),
    path("live/", LivenessHealthCheckView.as_view(), name="health-live"),
]

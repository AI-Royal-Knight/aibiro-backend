from unittest.mock import MagicMock, patch
from django.test import Client, TestCase
from django.urls import reverse


class HealthCheckTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_overall_health_endpoint_success(self):
        """Test GET /api/health/ returns 200 and expected healthy structure."""
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("timestamp", data)
        self.assertIn("services", data)
        self.assertIn("database", data["services"])
        self.assertIn("cache", data["services"])
        self.assertIn("storage", data["services"])
        self.assertIn("system", data)

        # Verify DB check inside overall health
        self.assertEqual(data["services"]["database"]["default"]["status"], "healthy")
        self.assertGreaterEqual(data["services"]["database"]["default"]["latency_ms"], 0)

    def test_database_health_endpoint_success(self):
        """Test GET /api/health/db/ returns 200 and database health details."""
        response = self.client.get("/api/health/db/")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("databases", data)
        self.assertEqual(data["databases"]["default"]["status"], "healthy")

    def test_liveness_endpoint_success(self):
        """Test GET /api/health/live/ returns 200 and alive status."""
        response = self.client.get("/api/health/live/")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["status"], "alive")
        self.assertIn("timestamp", data)

    def test_health_root_prefix_aliases(self):
        """Test /health/ endpoint works identically to /api/health/."""
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "healthy")

    @patch("django.db.backends.utils.CursorWrapper")
    def test_database_failure_returns_503(self, mock_cursor_wrapper):
        """Test that a database outage causes a 503 response with error details."""
        from django.db import DatabaseError

        with patch("app.common.health.connections") as mock_connections:
            mock_conn = MagicMock()
            mock_conn.cursor.side_effect = DatabaseError("Connection refused to database")
            mock_conn.vendor = "postgresql"
            mock_connections.databases = ["default"]
            mock_connections.__getitem__.return_value = mock_conn

            # Test /api/health/
            response = self.client.get("/api/health/")
            self.assertEqual(response.status_code, 503)
            data = response.json()
            self.assertEqual(data["status"], "unhealthy")
            self.assertEqual(data["services"]["database"]["default"]["status"], "unhealthy")
            self.assertIn("Connection refused", data["services"]["database"]["default"]["error"])

            # Test /api/health/db/
            db_response = self.client.get("/api/health/db/")
            self.assertEqual(db_response.status_code, 503)
            db_data = db_response.json()
            self.assertEqual(db_data["status"], "unhealthy")
            self.assertEqual(db_data["databases"]["default"]["status"], "unhealthy")


class BaseModelTests(TestCase):
    def test_base_model_is_abstract(self):
        """Verify BaseModel is an abstract model."""
        from app.common.models import BaseModel

        self.assertTrue(BaseModel._meta.abstract)

    def test_concrete_subclass_has_expected_fields(self):
        """Verify that concrete models inheriting from BaseModel have id, created_at, and updated_at."""
        import uuid
        from django.db import models
        from app.common.models import BaseModel

        class ConcreteItem(BaseModel):
            title = models.CharField(max_length=100)

            class Meta:
                app_label = "common"

        # Check fields exist on the model
        field_names = [f.name for f in ConcreteItem._meta.fields]
        self.assertIn("id", field_names)
        self.assertIn("created_at", field_names)
        self.assertIn("updated_at", field_names)

        # Check field types and attributes
        id_field = ConcreteItem._meta.get_field("id")
        self.assertTrue(id_field.primary_key)
        self.assertFalse(id_field.editable)
        self.assertEqual(id_field.default, uuid.uuid4)

        created_field = ConcreteItem._meta.get_field("created_at")
        self.assertTrue(created_field.auto_now_add)
        self.assertTrue(created_field.db_index)

        updated_field = ConcreteItem._meta.get_field("updated_at")
        self.assertTrue(updated_field.auto_now)

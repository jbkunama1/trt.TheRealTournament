import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


class ApiFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_dir = tempfile.TemporaryDirectory()
        os.environ.update({
            "DATA_DIR": cls.data_dir.name,
            "DB_PATH": str(Path(cls.data_dir.name) / "trt.db"),
            "UPLOAD_DIR": str(Path(cls.data_dir.name) / "uploads"),
            "ADMIN_USER": "test-admin",
            "ADMIN_PASSWORD": "initial-password",
            "SEED_DEMO": "false",
        })
        from app.main import app
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.data_dir.cleanup()

    def setUp(self):
        response = self.client.post(
            "/api/auth/login",
            json={"username": "test-admin", "password": "initial-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.headers = {"X-Token": response.json()["token"]}

    def test_reader_cannot_write(self):
        response = self.client.post(
            "/api/users",
            headers=self.headers,
            json={"username": "reader", "password": "reader-pass", "role": "leser"},
        )
        self.assertEqual(response.status_code, 200)
        token = self.client.post(
            "/api/auth/login",
            json={"username": "reader", "password": "reader-pass"},
        ).json()["token"]
        blocked = self.client.post(
            "/api/teams", headers={"X-Token": token}, json={"name": "Blocked"}
        )
        self.assertEqual(blocked.status_code, 403)

    def test_password_change_requires_current_password(self):
        wrong = self.client.put(
            "/api/auth/me/password",
            headers=self.headers,
            json={"current_password": "wrong", "new_password": "new-password"},
        )
        self.assertEqual(wrong.status_code, 400)
        short = self.client.put(
            "/api/auth/me/password",
            headers=self.headers,
            json={"current_password": "initial-password", "new_password": "short"},
        )
        self.assertEqual(short.status_code, 400)

    def test_team_image_can_be_uploaded_and_removed(self):
        team = self.client.post(
            "/api/teams", headers=self.headers, json={"name": "Image Team"}
        ).json()
        uploaded = self.client.post(
            f"/api/teams/{team['id']}/logo",
            headers=self.headers,
            files={"file": ("team.png", b"test-image", "image/png")},
        )
        self.assertEqual(uploaded.status_code, 200)
        removed = self.client.delete(
            f"/api/teams/{team['id']}/logo", headers=self.headers
        )
        self.assertEqual(removed.status_code, 200)

    def test_missing_export_returns_not_found(self):
        response = self.client.get("/api/tournaments/999/export.ics", headers=self.headers)
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()

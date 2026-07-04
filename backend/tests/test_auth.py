"""P1.5 — Auth tests."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
    needs_rehash,
    get_auth_mode,
)


class AuthServiceTests(unittest.TestCase):

    def test_password_hash_and_verify(self) -> None:
        h = hash_password("testpass123")
        self.assertTrue(verify_password("testpass123", h))
        self.assertFalse(verify_password("wrongpass", h))

    def test_password_needs_rehash(self) -> None:
        h = hash_password("testpass456")
        self.assertFalse(needs_rehash(h))

    def test_access_token_creation(self) -> None:
        token = create_access_token("uid1", "t1", "lawyer", "s1")
        payload = decode_token(token, "access")
        self.assertEqual(payload["sub"], "uid1")
        self.assertEqual(payload["tenant_id"], "t1")
        self.assertEqual(payload["role"], "lawyer")

    def test_refresh_token_creation(self) -> None:
        token = create_refresh_token("uid2", "s2", "fam1")
        payload = decode_token(token, "refresh")
        self.assertEqual(payload["sub"], "uid2")

    def test_access_token_rejected_in_refresh(self) -> None:
        token = create_access_token("uid3", "t2", "lawyer")
        with self.assertRaises(Exception):
            decode_token(token, "refresh")

    def test_refresh_token_rejected_in_access(self) -> None:
        token = create_refresh_token("uid4", "s3", "fam2")
        with self.assertRaises(Exception):
            decode_token(token, "access")

    def test_local_auth_mode(self) -> None:
        self.assertEqual(get_auth_mode(), "local")


class AuthEndpointTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_login_local_returns_token(self) -> None:
        response = self.client.post("/auth/login", json={"email": "test@test.com", "password": "test"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("access_token", data)

    def test_me_returns_user_info(self) -> None:
        response = self.client.get("/auth/me")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("user_id", data)
        self.assertIn("tenant_id", data)
        self.assertEqual(data["auth_mode"], "local")

    def test_refresh_returns_token(self) -> None:
        response = self.client.post("/auth/refresh", json={"refresh_token": "test"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("access_token", response.json())

    def test_logout_returns_ok(self) -> None:
        response = self.client.post("/auth/logout")
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()

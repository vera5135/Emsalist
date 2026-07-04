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


class JWTTokenValidationTests(unittest.TestCase):

    def test_expired_token_rejected(self) -> None:
        import jwt as pyjwt
        from datetime import UTC, datetime, timedelta
        token = pyjwt.encode(
            {"sub": "u1", "tenant_id": "t1", "role": "lawyer", "token_type": "access",
             "iss": "emsalist", "exp": datetime.now(UTC) - timedelta(minutes=1), "iat": datetime.now(UTC)},
            "emsalist-local-dev-key-change-in-production", algorithm="HS256",
        )
        from app.services.auth_service import decode_token
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            decode_token(token, "access")

    def test_wrong_issuer_rejected(self) -> None:
        import jwt as pyjwt
        from datetime import UTC, datetime, timedelta
        token = pyjwt.encode(
            {"sub": "u1", "tenant_id": "t1", "role": "lawyer", "token_type": "access",
             "iss": "wrong", "exp": datetime.now(UTC) + timedelta(minutes=30), "iat": datetime.now(UTC)},
            "emsalist-local-dev-key-change-in-production", algorithm="HS256",
        )
        from app.services.auth_service import decode_token
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            decode_token(token, "access")

    def test_alg_none_rejected(self) -> None:
        import jwt as pyjwt
        from fastapi import HTTPException
        from app.services.auth_service import decode_token
        with self.assertRaises(Exception):
            decode_token("eyJhbGciOiJub25lIn0.eyJzdWIiOiJ1MSJ9.", "access")

    def test_token_type_enforcement(self) -> None:
        from app.services.auth_service import create_access_token
        token = create_access_token("u1", "t1", "lawyer")
        from app.services.auth_service import decode_token
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            decode_token(token, "refresh")

    def test_missing_claims_rejected(self) -> None:
        import jwt as pyjwt
        from datetime import UTC, datetime, timedelta
        from fastapi import HTTPException
        from app.services.auth_service import decode_token
        token = pyjwt.encode(
            {"sub": "u1", "exp": datetime.now(UTC) + timedelta(minutes=30), "iat": datetime.now(UTC)},
            "emsalist-local-dev-key-change-in-production", algorithm="HS256",
        )
        with self.assertRaises(Exception):
            decode_token(token, "access")

    def test_wrong_signature_rejected(self) -> None:
        import jwt as pyjwt
        from datetime import UTC, datetime, timedelta
        from fastapi import HTTPException
        from app.services.auth_service import decode_token
        token = pyjwt.encode(
            {"sub": "u1", "tenant_id": "t1", "role": "lawyer", "token_type": "access",
             "iss": "emsalist", "exp": datetime.now(UTC) + timedelta(minutes=30), "iat": datetime.now(UTC)},
            "wrong-secret-key-that-does-not-match", algorithm="HS256",
        )
        with self.assertRaises(Exception):
            decode_token(token, "access")


class TenantIsolationTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        from app.services.case_session_service import case_session_service
        cls.case_a = case_session_service.new_case()["case_id"]
        cls.case_b = case_session_service.new_case()["case_id"]

    def test_case_a_data_not_in_case_b(self) -> None:
        from app.services.case_session_service import case_session_service
        from app.services.precedent_authority_service import precedent_authority_service
        live = [{"court": "Yargitay 13. HD", "esas_no": "2023/iso", "karar_no": "2024/iso", "date": "01.01.2024",
                 "title": "ayipli arac satisi", "profile_id": "car", "case_summary": "arac"}]
        a = precedent_authority_service.build_authority(case_id=self.case_a, live_results=live, brain_results=[])
        case_session_service.update_case(self.case_a, precedent_authority=a.model_dump(mode="json"))
        state_b = case_session_service.get_case_state(self.case_b)
        auth = state_b.get("precedent_authority", {})
        records = auth.get("records", [])
        self.assertEqual(len(records), 0)

    def test_case_b_data_not_in_case_a(self) -> None:
        from app.services.case_session_service import case_session_service
        from app.services.precedent_authority_service import precedent_authority_service
        live = [{"court": "Yargitay 9. HD", "esas_no": "2024/bbb", "karar_no": "2025/bbb", "date": "01.01.2025",
                 "title": "iscilik alacagi", "profile_id": "labor", "case_summary": "iscilik"}]
        a = precedent_authority_service.build_authority(case_id=self.case_b, live_results=live, brain_results=[])
        case_session_service.update_case(self.case_b, precedent_authority=a.model_dump(mode="json"))
        state_a = case_session_service.get_case_state(self.case_a)
        auth = state_a.get("precedent_authority", {})
        records = auth.get("records", [])
        self.assertNotIn("2024/bbb", str(records))


if __name__ == "__main__":
    unittest.main()

"""P1.5.3 — Comprehensive auth, session and ownership tests."""
from __future__ import annotations
import unittest, os

from fastapi.testclient import TestClient
from app.main import app
from app.services.auth_service import (
    create_access_token, create_refresh_token, decode_token,
    hash_password, verify_password, check_login_rate, reset_login_rate,
    check_production_safety, get_auth_mode,
)

class JWTValidationTests(unittest.TestCase):
    def test_valid_token_accepted(self):
        t = create_access_token("u1", "t1", "lawyer", "s1")
        p = decode_token(t, "access")
        self.assertEqual(p["sub"], "u1")
        self.assertEqual(p["aud"], "emsalist-api")

    def test_expired_rejected(self):
        import jwt as j; from datetime import UTC, datetime, timedelta
        t = j.encode({"sub":"u","tenant_id":"t","role":"l","token_type":"access","iss":"emsalist","aud":"emsalist-api","nbf":datetime.now(UTC),"iat":datetime.now(UTC),"exp":datetime.now(UTC)-timedelta(minutes=1)}, "emsalist-local-dev-key-change-in-production", algorithm="HS256")
        from fastapi import HTTPException
        with self.assertRaises(HTTPException): decode_token(t)

    def test_wrong_audience(self):
        import jwt as j; from datetime import UTC, datetime, timedelta
        n = datetime.now(UTC)
        t = j.encode({"sub":"u","tenant_id":"t","role":"l","token_type":"access","iss":"emsalist","aud":"wrong","nbf":n,"iat":n,"exp":n+timedelta(minutes=30)}, "emsalist-local-dev-key-change-in-production", algorithm="HS256")
        from fastapi import HTTPException
        with self.assertRaises(HTTPException): decode_token(t)

    def test_missing_aud(self):
        import jwt as j; from datetime import UTC, datetime, timedelta
        n = datetime.now(UTC)
        t = j.encode({"sub":"u","tenant_id":"t","role":"l","token_type":"access","iss":"emsalist","nbf":n,"iat":n,"exp":n+timedelta(minutes=30)}, "emsalist-local-dev-key-change-in-production", algorithm="HS256")
        from fastapi import HTTPException
        with self.assertRaises(Exception): decode_token(t)

    def test_nbf_future(self):
        import jwt as j; from datetime import UTC, datetime, timedelta
        n = datetime.now(UTC)
        f = n + timedelta(minutes=10)
        t = j.encode({"sub":"u","tenant_id":"t","role":"l","token_type":"access","iss":"emsalist","aud":"emsalist-api","nbf":f,"iat":n,"exp":f+timedelta(minutes=30)}, "emsalist-local-dev-key-change-in-production", algorithm="HS256")
        from fastapi import HTTPException
        with self.assertRaises(HTTPException): decode_token(t)

    def test_alg_none_rejected(self):
        from fastapi import HTTPException
        with self.assertRaises(Exception): decode_token("eyJhbGciOiJub25lIn0.eyJzdWIiOiJ1MSJ9.", "access")

    def test_wrong_signature(self):
        import jwt as j; from datetime import UTC, datetime, timedelta
        n = datetime.now(UTC)
        t = j.encode({"sub":"u","tenant_id":"t","role":"l","token_type":"access","iss":"emsalist","aud":"emsalist-api","nbf":n,"iat":n,"exp":n+timedelta(minutes=30)},"wrong-secret-key-xxxxxx--should-be-32-bytes", algorithm="HS256")
        from fastapi import HTTPException
        with self.assertRaises(Exception): decode_token(t)

    def test_wrong_issuer(self):
        import jwt as j; from datetime import UTC, datetime, timedelta
        n = datetime.now(UTC)
        t = j.encode({"sub":"u","tenant_id":"t","role":"l","token_type":"access","iss":"wrong","aud":"emsalist-api","nbf":n,"iat":n,"exp":n+timedelta(minutes=30)},"emsalist-local-dev-key-change-in-production", algorithm="HS256")
        from fastapi import HTTPException
        with self.assertRaises(HTTPException): decode_token(t)

    def test_refresh_rejected_as_access(self):
        t = create_refresh_token("u1", "s1", "fam1")
        from fastapi import HTTPException
        with self.assertRaises(HTTPException): decode_token(t, "access")

    def test_access_rejected_as_refresh(self):
        t = create_access_token("u1", "t1", "lawyer")
        from fastapi import HTTPException
        with self.assertRaises(HTTPException): decode_token(t, "refresh")


class RateLimitTests(unittest.TestCase):
    def setUp(self): reset_login_rate("test-key")
    def test_allows_under_limit(self):
        for _ in range(3): limited, _ = check_login_rate("rl-test"); self.assertFalse(limited)
    def test_blocks_over_limit(self):
        k = "rl-block"
        for _ in range(5): check_login_rate(k)
        limited, retry = check_login_rate(k); self.assertTrue(limited); self.assertGreater(retry, 0)
    def test_reset_clears(self):
        k = "rl-reset"
        for _ in range(3): check_login_rate(k)
        reset_login_rate(k)
        limited, _ = check_login_rate(k); self.assertFalse(limited)
    def test_isolation(self):
        for _ in range(5): check_login_rate("rl-a")
        limited, _ = check_login_rate("rl-b"); self.assertFalse(limited)


class ProductionSafetyTests(unittest.TestCase):
    def test_local_mode_detected(self):
        issues = check_production_safety()
        if get_auth_mode() == "local": self.assertGreater(len(issues), 0)

    def test_secret_validation(self):
        issues = check_production_safety()
        self.assertIsInstance(issues, list)


class CrossTenantIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.services.case_session_service import case_session_service
        cls.case_a = case_session_service.new_case()["case_id"]
        cls.case_b = case_session_service.new_case()["case_id"]

    def test_case_a_precedent_not_in_b(self):
        from app.services.case_session_service import case_session_service
        from app.services.precedent_authority_service import precedent_authority_service
        live = [{"court":"Yargitay 13. HD","esas_no":"2023/AAA","karar_no":"2024/AAA","date":"01.01.2024","title":"arac","profile_id":"car","case_summary":"arac"}]
        a = precedent_authority_service.build_authority(case_id=self.case_a, live_results=live, brain_results=[])
        case_session_service.update_case(self.case_a, precedent_authority=a.model_dump(mode="json"))
        state_b = case_session_service.get_case_state(self.case_b)
        recs = state_b.get("precedent_authority", {}).get("records", [])
        self.assertEqual(len(recs), 0)

    def test_case_b_precedent_not_in_a(self):
        from app.services.case_session_service import case_session_service
        from app.services.precedent_authority_service import precedent_authority_service
        live = [{"court":"Yargitay 9. HD","esas_no":"2024/BBB","karar_no":"2025/BBB","date":"01.01.2025","title":"iscilik","profile_id":"labor","case_summary":"iscilik"}]
        a = precedent_authority_service.build_authority(case_id=self.case_b, live_results=live, brain_results=[])
        case_session_service.update_case(self.case_b, precedent_authority=a.model_dump(mode="json"))
        state_a = case_session_service.get_case_state(self.case_a)
        recs = state_a.get("precedent_authority", {}).get("records", [])
        self.assertNotIn("2024/BBB", str(recs))


class AuthEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.client = TestClient(app)
    def test_login_local(self):
        r = self.client.post("/auth/login", json={"email":"t@t.com","password":"t"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("access_token", data)
        self.assertIn("refresh_token", data)
        self.assertIn("expires_in", data)
        self.assertIn("refresh_expires_in", data)
        self.assertIn("user", data)

    def test_login_refresh_token_differs_from_access(self):
        r = self.client.post("/auth/login", json={"email":"t@t.com","password":"t"})
        data = r.json()
        self.assertNotEqual(data["access_token"], data["refresh_token"])

    def test_me(self):
        r = self.client.get("/auth/me")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("user_id", data)
        self.assertIn("auth_mode", data)
        self.assertIn("authenticated", data)

    def test_refresh_with_body(self):
        r = self.client.post("/auth/refresh", json={"refresh_token":"test-refresh-token"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("access_token", data)
        self.assertIn("refresh_token", data)
        self.assertIn("expires_in", data)
        self.assertIn("refresh_expires_in", data)

    def test_refresh_missing_token(self):
        r = self.client.post("/auth/refresh", json={})
        self.assertEqual(r.status_code, 422)

    def test_logout(self):
        r = self.client.post("/auth/logout"); self.assertEqual(r.status_code, 200)

    def test_logout_all(self):
        r = self.client.post("/auth/logout-all"); self.assertEqual(r.status_code, 200)

    def test_change_password_local(self):
        r = self.client.post("/auth/change-password", json={"current_password":"old","new_password":"new-secure-8-chars"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Not available in local mode", r.json()["message"])

    def test_token_expires_in_header(self):
        r = self.client.post("/auth/login", json={"email":"t@t.com","password":"t"})
        data = r.json()
        self.assertEqual(data["expires_in"], 1800)
        self.assertEqual(data["refresh_expires_in"], 604800)

    def test_refresh_expires_in_header(self):
        r = self.client.post("/auth/refresh", json={"refresh_token":"t"})
        data = r.json()
        self.assertEqual(data["expires_in"], 1800)
        self.assertEqual(data["refresh_expires_in"], 604800)


if __name__ == "__main__": unittest.main()

"""P2.2B2A — Apple auth backend tests.

Tests use mocked HTTP/Apple services. No real Apple network calls.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_service import (
    create_access_token, get_auth_mode, hash_password,
)


class AppleSubjectHashTests(unittest.TestCase):
    def test_subject_hash_deterministic(self):
        from app.services.apple_auth_service import hash_apple_subject
        with patch("app.services.apple_auth_service.get_settings") as mock_settings:
            mock_settings.return_value.apple_subject_pepper = "a" * 32
            h1 = hash_apple_subject("com.example.app", "001234.abcdef")
            h2 = hash_apple_subject("com.example.app", "001234.abcdef")
            self.assertEqual(h1, h2)

    def test_subject_hash_different_inputs(self):
        from app.services.apple_auth_service import hash_apple_subject
        with patch("app.services.apple_auth_service.get_settings") as mock_settings:
            mock_settings.return_value.apple_subject_pepper = "a" * 32
            h1 = hash_apple_subject("com.example.app", "001234.abcdef")
            h2 = hash_apple_subject("com.example.app", "001234.ghijkl")
            self.assertNotEqual(h1, h2)

    def test_subject_hash_no_pepper_raises(self):
        from app.services.apple_auth_service import hash_apple_subject, AppleAuthError
        with patch("app.services.apple_auth_service.get_settings") as mock_settings:
            mock_settings.return_value.apple_subject_pepper = ""
            with self.assertRaises(AppleAuthError):
                hash_apple_subject("com.example.app", "001234.abcdef")


class AppleClientSecretTests(unittest.TestCase):
    def test_client_secret_valid_structure(self):
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        import jwt as pyjwt

        private_key = ec.generate_private_key(ec.SECP256R1())
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        with patch("app.services.apple_auth_service.get_settings") as mock_settings, \
             patch("app.services.apple_auth_service._load_private_key", return_value=pem):
            mock_settings.return_value.apple_team_id = "TEAM123"
            mock_settings.return_value.apple_client_id = "com.example.app"
            mock_settings.return_value.apple_key_id = "KEY456"
            mock_settings.return_value.apple_private_key_path = "/fake/key.p8"
            mock_settings.return_value.apple_subject_pepper = "a" * 32

            from app.services.apple_auth_service import generate_client_secret, _client_secret_cache
            _client_secret_cache = None
            secret = generate_client_secret()

            unverified = pyjwt.decode(secret, options={"verify_signature": False})
            header = pyjwt.get_unverified_header(secret)

            self.assertEqual(header["alg"], "ES256")
            self.assertEqual(header["kid"], "KEY456")
            self.assertEqual(unverified["iss"], "TEAM123")
            self.assertEqual(unverified["sub"], "com.example.app")
            self.assertEqual(unverified["aud"], "https://appleid.apple.com")
            self.assertIn("iat", unverified)
            self.assertIn("exp", unverified)
            self.assertLessEqual(unverified["exp"] - unverified["iat"], 300)

    def test_client_secret_cached(self):
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization

        private_key = ec.generate_private_key(ec.SECP256R1())
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        with patch("app.services.apple_auth_service.get_settings") as mock_settings, \
             patch("app.services.apple_auth_service._load_private_key", return_value=pem):
            mock_settings.return_value.apple_team_id = "TEAM123"
            mock_settings.return_value.apple_client_id = "com.example.app"
            mock_settings.return_value.apple_key_id = "KEY456"
            mock_settings.return_value.apple_private_key_path = "/fake/key.p8"
            mock_settings.return_value.apple_subject_pepper = "a" * 32

            from app.services.apple_auth_service import generate_client_secret, _client_secret_cache
            _client_secret_cache = None
            s1 = generate_client_secret()
            s2 = generate_client_secret()
            self.assertEqual(s1, s2)


class AppleTokenExchangeTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_exchange(self):
        from app.services.apple_auth_service import exchange_authorization_code
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "at123",
            "id_token": "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJzMSJ9.signature",
        }

        with patch("app.services.apple_auth_service.get_settings") as mock_settings, \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_settings.return_value.apple_sign_in_enabled = True
            mock_settings.return_value.apple_client_id = "com.example.app"
            mock_settings.return_value.apple_token_endpoint = "https://test.apple.com/token"
            mock_settings.return_value.apple_http_timeout_seconds = 5

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await exchange_authorization_code("authcode123")
            self.assertEqual(result["id_token"], "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJzMSJ9.signature")

    async def test_disabled_raises(self):
        from app.services.apple_auth_service import exchange_authorization_code, AppleAuthError
        with patch("app.services.apple_auth_service.get_settings") as mock_settings:
            mock_settings.return_value.apple_sign_in_enabled = False
            with self.assertRaises(AppleAuthError) as ctx:
                await exchange_authorization_code("code")
            self.assertEqual(ctx.exception.code, "apple_sign_in_unavailable")

    async def test_timeout_raises(self):
        from app.services.apple_auth_service import exchange_authorization_code, AppleAuthError
        with patch("app.services.apple_auth_service.get_settings") as mock_settings, \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_settings.return_value.apple_sign_in_enabled = True
            mock_settings.return_value.apple_http_timeout_seconds = 5

            import httpx
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post.side_effect = httpx.TimeoutException("timeout")
            mock_client_cls.return_value = mock_client

            with self.assertRaises(AppleAuthError) as ctx:
                await exchange_authorization_code("code")
            self.assertEqual(ctx.exception.code, "apple_authorization_failed")

    async def test_4xx_raises(self):
        from app.services.apple_auth_service import exchange_authorization_code, AppleAuthError
        from unittest.mock import MagicMock

        with patch("app.services.apple_auth_service.get_settings") as mock_settings, \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_settings.return_value.apple_sign_in_enabled = True

            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.json.return_value = {"error": "invalid_grant"}
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            with self.assertRaises(AppleAuthError) as ctx:
                await exchange_authorization_code("code")
            self.assertEqual(ctx.exception.code, "apple_authorization_failed")

    async def test_missing_id_token_raises(self):
        from app.services.apple_auth_service import exchange_authorization_code, AppleAuthError
        from unittest.mock import MagicMock

        with patch("app.services.apple_auth_service.get_settings") as mock_settings, \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_settings.return_value.apple_sign_in_enabled = True

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"access_token": "at"}
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            with self.assertRaises(AppleAuthError) as ctx:
                await exchange_authorization_code("code")
            self.assertEqual(ctx.exception.code, "apple_authorization_failed")


class AppleIdTokenVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        import jwt as pyjwt

        cls._rsa_key = rsa.generate_private_key(65537, 2048)
        cls._public_key = cls._rsa_key.public_key()
        cls._public_pem = cls._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

        cls._kid = "test-key-1"
        cls._n_bytes = cls._rsa_key.private_numbers().public_numbers.n
        cls._e_bytes = cls._rsa_key.private_numbers().public_numbers.e
        import base64
        import math
        n_b64 = base64.urlsafe_b64encode(cls._n_bytes.to_bytes(math.ceil(cls._n_bytes.bit_length() / 8), "big")).rstrip(b"=").decode()
        e_b64 = base64.urlsafe_b64encode(cls._e_bytes.to_bytes(math.ceil(cls._e_bytes.bit_length() / 8), "big")).rstrip(b"=").decode()

        cls._jwks = {
            "keys": [{
                "kty": "RSA",
                "kid": cls._kid,
                "use": "sig",
                "alg": "RS256",
                "n": n_b64,
                "e": e_b64,
            }]
        }

    def _sign_token(self, claims: dict, kid: str | None = None) -> str:
        import jwt as pyjwt
        headers = {"alg": "RS256"}
        if kid:
            headers["kid"] = kid
        return pyjwt.encode(claims, self._rsa_key, algorithm="RS256", headers=headers)

    def test_valid_token_accepted(self):
        from app.services.apple_auth_service import verify_apple_id_token

        nonce_raw = "test-nonce-12345"
        nonce_hashed = hashlib.sha256(nonce_raw.encode()).hexdigest()
        now = int(time.time())
        claims = {
            "iss": "https://appleid.apple.com",
            "aud": "com.example.app",
            "sub": "001234.abcdef",
            "iat": now - 10,
            "exp": now + 3600,
            "nonce": nonce_hashed,
            "nonce_supported": True,
        }
        token = self._sign_token(claims, kid=self._kid)

        with patch("app.services.apple_auth_service._get_jwks", return_value=self._jwks), \
             patch("app.services.apple_auth_service.get_settings") as mock_settings:
            mock_settings.return_value.apple_issuer = "https://appleid.apple.com"
            mock_settings.return_value.apple_client_id = "com.example.app"
            mock_settings.return_value.apple_jwks_url = "https://test/jwks"
            mock_settings.return_value.apple_http_timeout_seconds = 5

            payload = verify_apple_id_token(token, nonce_raw)
            self.assertEqual(payload["sub"], "001234.abcdef")

    def test_wrong_issuer_rejected(self):
        from app.services.apple_auth_service import verify_apple_id_token, AppleAuthError

        nonce_raw = "test-nonce"
        nonce_hashed = hashlib.sha256(nonce_raw.encode()).hexdigest()
        now = int(time.time())
        claims = {
            "iss": "https://wrong.com",
            "aud": "com.example.app",
            "sub": "001234.abcdef",
            "iat": now - 10,
            "exp": now + 3600,
            "nonce": nonce_hashed,
        }
        token = self._sign_token(claims, kid=self._kid)

        with patch("app.services.apple_auth_service._get_jwks", return_value=self._jwks), \
             patch("app.services.apple_auth_service.get_settings") as mock_settings:
            mock_settings.return_value.apple_issuer = "https://appleid.apple.com"
            mock_settings.return_value.apple_client_id = "com.example.app"
            with self.assertRaises(AppleAuthError):
                verify_apple_id_token(token, nonce_raw)

    def test_wrong_audience_rejected(self):
        from app.services.apple_auth_service import verify_apple_id_token, AppleAuthError

        nonce_raw = "test-nonce"
        nonce_hashed = hashlib.sha256(nonce_raw.encode()).hexdigest()
        now = int(time.time())
        claims = {
            "iss": "https://appleid.apple.com",
            "aud": "com.wrong.app",
            "sub": "001234.abcdef",
            "iat": now - 10,
            "exp": now + 3600,
            "nonce": nonce_hashed,
        }
        token = self._sign_token(claims, kid=self._kid)

        with patch("app.services.apple_auth_service._get_jwks", return_value=self._jwks), \
             patch("app.services.apple_auth_service.get_settings") as mock_settings:
            mock_settings.return_value.apple_issuer = "https://appleid.apple.com"
            mock_settings.return_value.apple_client_id = "com.example.app"
            with self.assertRaises(AppleAuthError):
                verify_apple_id_token(token, nonce_raw)

    def test_expired_token_rejected(self):
        from app.services.apple_auth_service import verify_apple_id_token, AppleAuthError

        nonce_raw = "test-nonce"
        nonce_hashed = hashlib.sha256(nonce_raw.encode()).hexdigest()
        now = int(time.time())
        claims = {
            "iss": "https://appleid.apple.com",
            "aud": "com.example.app",
            "sub": "001234.abcdef",
            "iat": now - 7200,
            "exp": now - 3600,
            "nonce": nonce_hashed,
        }
        token = self._sign_token(claims, kid=self._kid)

        with patch("app.services.apple_auth_service._get_jwks", return_value=self._jwks), \
             patch("app.services.apple_auth_service.get_settings") as mock_settings:
            mock_settings.return_value.apple_issuer = "https://appleid.apple.com"
            mock_settings.return_value.apple_client_id = "com.example.app"
            with self.assertRaises(AppleAuthError):
                verify_apple_id_token(token, nonce_raw)

    def test_missing_sub_rejected(self):
        from app.services.apple_auth_service import verify_apple_id_token, AppleAuthError

        nonce_raw = "test-nonce"
        nonce_hashed = hashlib.sha256(nonce_raw.encode()).hexdigest()
        now = int(time.time())
        claims = {
            "iss": "https://appleid.apple.com",
            "aud": "com.example.app",
            "iat": now - 10,
            "exp": now + 3600,
            "nonce": nonce_hashed,
        }
        token = self._sign_token(claims, kid=self._kid)

        with patch("app.services.apple_auth_service._get_jwks", return_value=self._jwks), \
             patch("app.services.apple_auth_service.get_settings") as mock_settings:
            mock_settings.return_value.apple_issuer = "https://appleid.apple.com"
            mock_settings.return_value.apple_client_id = "com.example.app"
            with self.assertRaises(AppleAuthError):
                verify_apple_id_token(token, nonce_raw)

    def test_wrong_alg_rejected(self):
        from app.services.apple_auth_service import verify_apple_id_token, AppleAuthError
        import jwt as pyjwt

        nonce_raw = "test-nonce"
        nonce_hashed = hashlib.sha256(nonce_raw.encode()).hexdigest()
        now = int(time.time())
        claims = {
            "iss": "https://appleid.apple.com",
            "aud": "com.example.app",
            "sub": "001234.abcdef",
            "iat": now - 10,
            "exp": now + 3600,
            "nonce": nonce_hashed,
        }
        token = pyjwt.encode(claims, "secret", algorithm="HS256", headers={"alg": "HS256"})

        with patch("app.services.apple_auth_service.get_settings") as mock_settings:
            with self.assertRaises(AppleAuthError):
                verify_apple_id_token(token, nonce_raw)

    def test_missing_nonce_rejected(self):
        from app.services.apple_auth_service import verify_apple_id_token, AppleAuthError

        now = int(time.time())
        claims = {
            "iss": "https://appleid.apple.com",
            "aud": "com.example.app",
            "sub": "001234.abcdef",
            "iat": now - 10,
            "exp": now + 3600,
        }
        token = self._sign_token(claims, kid=self._kid)

        with patch("app.services.apple_auth_service._get_jwks", return_value=self._jwks), \
             patch("app.services.apple_auth_service.get_settings") as mock_settings:
            mock_settings.return_value.apple_issuer = "https://appleid.apple.com"
            mock_settings.return_value.apple_client_id = "com.example.app"
            with self.assertRaises(AppleAuthError):
                verify_apple_id_token(token, "any-nonce")

    def test_wrong_nonce_rejected(self):
        from app.services.apple_auth_service import verify_apple_id_token, AppleAuthError

        correct_nonce = hashlib.sha256(b"real-nonce").hexdigest()
        now = int(time.time())
        claims = {
            "iss": "https://appleid.apple.com",
            "aud": "com.example.app",
            "sub": "001234.abcdef",
            "iat": now - 10,
            "exp": now + 3600,
            "nonce": correct_nonce,
        }
        token = self._sign_token(claims, kid=self._kid)

        with patch("app.services.apple_auth_service._get_jwks", return_value=self._jwks), \
             patch("app.services.apple_auth_service.get_settings") as mock_settings:
            mock_settings.return_value.apple_issuer = "https://appleid.apple.com"
            mock_settings.return_value.apple_client_id = "com.example.app"
            with self.assertRaises(AppleAuthError):
                verify_apple_id_token(token, "wrong-nonce")

    def test_unknown_kid_triggers_refresh(self):
        from app.services.apple_auth_service import verify_apple_id_token, AppleAuthError

        nonce_raw = "test-nonce"
        nonce_hashed = hashlib.sha256(nonce_raw.encode()).hexdigest()
        now = int(time.time())
        claims = {
            "iss": "https://appleid.apple.com",
            "aud": "com.example.app",
            "sub": "001234.abcdef",
            "iat": now - 10,
            "exp": now + 3600,
            "nonce": nonce_hashed,
        }
        token = self._sign_token(claims, kid="unknown-kid")

        with patch("app.services.apple_auth_service._get_jwks", return_value=self._jwks), \
             patch("app.services.apple_auth_service._refresh_jwks_cache", return_value={"keys": []}), \
             patch("app.services.apple_auth_service.get_settings") as mock_settings:
            mock_settings.return_value.apple_issuer = "https://appleid.apple.com"
            mock_settings.return_value.apple_client_id = "com.example.app"
            with self.assertRaises(AppleAuthError):
                verify_apple_id_token(token, nonce_raw)


class LinkTicketTests(unittest.TestCase):
    def test_generate_ticket(self):
        from app.services.apple_auth_service import generate_link_ticket
        raw, ticket_hash = generate_link_ticket()
        self.assertIsNotNone(raw)
        self.assertIsNotNone(ticket_hash)
        self.assertEqual(len(raw), 96)
        self.assertEqual(len(ticket_hash), 64)
        self.assertEqual(hashlib.sha256(raw.encode()).hexdigest(), ticket_hash)

    def test_unique_tickets(self):
        from app.services.apple_auth_service import generate_link_ticket
        t1, _ = generate_link_ticket()
        t2, _ = generate_link_ticket()
        self.assertNotEqual(t1, t2)


class AppleAuthEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_apple_login_disabled_in_local_mode(self):
        r = self.client.post("/auth/apple/login", json={
            "authorization_code": "test-code",
            "raw_nonce": "test-nonce",
        })
        self.assertEqual(r.status_code, 503)

    def test_apple_link_disabled_in_local_mode(self):
        r = self.client.post("/auth/apple/link", json={
            "link_ticket": "ticket",
            "email": "test@test.com",
            "password": "pass",
        })
        self.assertEqual(r.status_code, 503)

    def test_apple_status_disabled_in_local_mode(self):
        r = self.client.get("/auth/apple/status")
        self.assertEqual(r.status_code, 503)

    def test_apple_unlink_disabled_in_local_mode(self):
        r = self.client.post("/auth/apple/unlink", json={"current_password": "pass"})
        self.assertEqual(r.status_code, 503)

    def test_login_without_tenant_slug_still_works_local(self):
        r = self.client.post("/auth/login", json={
            "email": "test@test.com",
            "password": "pass",
        })
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("access_token", data)

    def test_login_with_tenant_slug_null_works_local(self):
        r = self.client.post("/auth/login", json={
            "tenant_slug": None,
            "email": "test@test.com",
            "password": "pass",
        })
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()

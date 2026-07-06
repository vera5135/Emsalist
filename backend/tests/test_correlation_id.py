
from __future__ import annotations

import asyncio
import uuid

import pytest

from app.core.correlation import (
    generate_correlation_id,
    get_correlation_id,
    set_correlation_id,
    clear_correlation_id,
    sanitize_correlation_id,
    extract_or_create_correlation_id,
    MAX_CORRELATION_ID_LENGTH,
)


class TestCorrelationIdSanitization:

    def test_valid_uuid_preserved(self):
        cid = "abc123def456"
        result = sanitize_correlation_id(cid)
        assert result == cid

    def test_empty_string_returns_new_uuid(self):
        result = sanitize_correlation_id("")
        assert len(result) == 32
        assert result == uuid.UUID(hex=result, version=4).hex

    def test_none_returns_new_uuid(self):
        result = sanitize_correlation_id(None)
        assert len(result) == 32

    def test_too_long_value_rejected(self):
        long_val = "a" * (MAX_CORRELATION_ID_LENGTH + 1)
        result = sanitize_correlation_id(long_val)
        assert len(result) == 32

    def test_newline_character_rejected(self):
        result = sanitize_correlation_id("abc\n123")
        assert len(result) == 32
        assert "\n" not in result

    def test_carriage_return_rejected(self):
        result = sanitize_correlation_id("abc\r123")
        assert len(result) == 32
        assert "\r" not in result

    def test_control_characters_rejected(self):
        result = sanitize_correlation_id("abc\x00\x1f123")
        assert len(result) == 32

    def test_max_length_accepted(self):
        val = "a" * MAX_CORRELATION_ID_LENGTH
        result = sanitize_correlation_id(val)
        assert result == val


class TestCorrelationIdContext:

    def setup_method(self):
        clear_correlation_id()

    def test_generate_creates_hex_uuid(self):
        cid = generate_correlation_id()
        assert len(cid) == 32
        uuid.UUID(hex=cid, version=4)

    def test_set_and_get(self):
        set_correlation_id("test-123")
        assert get_correlation_id() == "test-123"

    def test_clear_removes_id(self):
        set_correlation_id("test-456")
        clear_correlation_id()
        assert get_correlation_id() == ""

    def test_extract_or_create_with_header(self):
        cid = extract_or_create_correlation_id("my-custom-id")
        assert cid == "my-custom-id"
        assert get_correlation_id() == "my-custom-id"

    def test_extract_or_create_with_none(self):
        cid = extract_or_create_correlation_id(None)
        assert len(cid) == 32
        assert get_correlation_id() == cid

    def test_extract_or_create_sanitizes_bad_input(self):
        cid = extract_or_create_correlation_id("bad\nvalue")
        assert "\n" not in cid
        assert get_correlation_id() == cid


class TestCorrelationIdIsolation:

    @pytest.mark.asyncio
    async def test_concurrent_requests_have_different_ids(self):

        async def request_with_id(task_id: str) -> str:
            cid = f"corr-{task_id}"
            set_correlation_id(cid)
            await asyncio.sleep(0.01)
            return get_correlation_id()

        results = await asyncio.gather(
            request_with_id("a"),
            request_with_id("b"),
            request_with_id("c"),
        )
        assert results[0] == "corr-a"
        assert results[1] == "corr-b"
        assert results[2] == "corr-c"

    def test_context_cleared_between_uses(self):
        set_correlation_id("first-id")
        assert get_correlation_id() == "first-id"
        clear_correlation_id()
        set_correlation_id("second-id")
        assert get_correlation_id() == "second-id"

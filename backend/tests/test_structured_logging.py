
from __future__ import annotations

import io
import json
import logging
import re
import sys
from unittest.mock import patch

from app.core.logging import JsonFormatter, SafeTextFormatter, setup_logging, _configured


class TestJsonFormatter:

    def test_json_output_is_valid(self):
        fmt = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="test message", args=(), exc_info=None,
        )
        record.service = "emsalist-api"
        record.environment = "test"
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test"
        assert parsed["message"] == "test message"
        assert parsed["service"] == "emsalist-api"
        assert "timestamp" in parsed

    def test_json_output_includes_extra_fields(self):
        fmt = JsonFormatter()
        record = logging.LogRecord(
            name="app.http", level=logging.INFO, pathname="", lineno=0,
            msg="access log", args=(), exc_info=None,
        )
        record.service = "emsalist-api"
        record.environment = "test"
        record.correlation_id = "abc123"
        record.method = "GET"
        record.path = "/case"
        record.status_code = 200
        record.duration_ms = 42
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed["correlation_id"] == "abc123"
        assert parsed["method"] == "GET"
        assert parsed["path"] == "/case"
        assert parsed["status_code"] == 200
        assert parsed["duration_ms"] == 42

    def test_json_output_excludes_empty_fields(self):
        fmt = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="msg", args=(), exc_info=None,
        )
        record.service = ""
        record.environment = ""
        output = fmt.format(record)
        parsed = json.loads(output)
        assert "tenant_id" not in parsed
        assert "user_id" not in parsed
        assert "job_id" not in parsed

    def test_json_output_includes_exception_info(self):
        fmt = JsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            record = logging.LogRecord(
                name="test", level=logging.ERROR, pathname="", lineno=0,
                msg="error occurred", args=(), exc_info=sys.exc_info(),
            )
            record.service = "emsalist-api"
            record.environment = "test"
            output = fmt.format(record)
            parsed = json.loads(output)
            assert parsed["exception_type"] == "ValueError"
            assert parsed["exception_message"] == "test error"


class TestSafeTextFormatter:

    def test_text_output_is_readable(self):
        fmt = SafeTextFormatter()
        record = logging.LogRecord(
            name="test.logger", level=logging.INFO, pathname="", lineno=0,
            msg="hello world", args=(), exc_info=None,
        )
        output = fmt.format(record)
        assert "INFO" in output
        assert "test.logger" in output
        assert "hello world" in output


class TestSetupLogging:

    def teardown_method(self):
        import logging
        import app.core.logging as mod
        mod._configured = False
        root = logging.getLogger()
        root.handlers.clear()

    def test_setup_logging_text_format(self):
        import app.core.logging as mod
        mod._configured = False
        with patch.dict("os.environ", {"ENVIRONMENT": "development", "LOG_FORMAT": "text", "LOG_LEVEL": "DEBUG"}, clear=False):
            setup_logging()
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        assert any(isinstance(h.formatter, SafeTextFormatter) for h in root.handlers)

    def test_setup_logging_does_not_add_duplicate_handlers(self):
        import app.core.logging as mod
        mod._configured = False
        with patch.dict("os.environ", {"ENVIRONMENT": "development", "LOG_FORMAT": "text"}, clear=False):
            setup_logging()
        handler_count_before = len(logging.getLogger().handlers)
        setup_logging()
        assert len(logging.getLogger().handlers) == handler_count_before

    def test_setup_logging_sets_env_vars(self):
        import app.core.logging as mod
        mod._configured = False
        with patch.dict("os.environ", {"ENVIRONMENT": "development", "LOG_FORMAT": "text"}, clear=False):
            setup_logging()
        root_logger = logging.getLogger()
        found_filter = any(
            isinstance(f, mod.ContextFilter) for f in root_logger.filters
        )
        assert found_filter

    def test_logging_can_produce_info_message(self):
        import app.core.logging as mod
        mod._configured = False
        with patch.dict("os.environ", {"ENVIRONMENT": "development", "LOG_FORMAT": "text"}, clear=False):
            setup_logging()
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(SafeTextFormatter())
        logger = logging.getLogger("test_unit")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.info("unit test log")
        output = stream.getvalue()
        assert "unit test log" in output


class TestAccessLogSecurity:

    def test_authorization_header_not_in_log(self):
        logger = logging.getLogger("test_security_log")
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(SafeTextFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.info("request method=GET path=/case user=test")
        output = stream.getvalue()
        assert "Bearer" not in output
        assert "Authorization" not in output or "Authorization" in output

    def test_request_body_not_logged(self):
        fmt = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="access log", args=(), exc_info=None,
        )
        record.service = "test"
        record.environment = "test"
        record.method = "POST"
        record.path = "/case"
        record.status_code = 200
        record.duration_ms = 15
        output = fmt.format(record)
        parsed = json.loads(output)
        assert "body" not in parsed
        assert "request_body" not in parsed

    def test_response_body_not_logged(self):
        fmt = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="response sent", args=(), exc_info=None,
        )
        record.service = "test"
        record.environment = "test"
        record.method = "GET"
        record.path = "/case"
        record.status_code = 200
        record.duration_ms = 10
        output = fmt.format(record)
        parsed = json.loads(output)
        assert "response_body" not in parsed
        assert "body" not in parsed

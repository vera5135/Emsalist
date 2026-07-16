"""Shared legal reasoning provider error types (no service imports; breaks import cycles)."""
from __future__ import annotations


class ReasoningProviderUnavailable(RuntimeError):
    pass

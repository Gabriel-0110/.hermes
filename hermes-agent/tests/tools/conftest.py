"""Shared test fixtures for tools tests."""
import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _stub_optional_audio_modules():
    """Inject stub modules for optional audio/ML dependencies not installed in
    the test environment.  Only activates when the real package is absent so
    that tests using the real library are unaffected.
    """
    injected: list[str] = []

    if "faster_whisper" not in sys.modules:
        stub = ModuleType("faster_whisper")
        stub.WhisperModel = MagicMock()  # type: ignore[attr-defined]
        sys.modules["faster_whisper"] = stub
        injected.append("faster_whisper")

    yield

    for name in injected:
        sys.modules.pop(name, None)

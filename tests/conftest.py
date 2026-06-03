"""Shared pytest fixtures for KCom test suite."""
from __future__ import annotations

import sys
import os

# Ensure the project root is on sys.path so `kcom` is importable.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication required by all Qt-dependent tests."""
    app = QApplication.instance() or QApplication(sys.argv[:1])
    yield app

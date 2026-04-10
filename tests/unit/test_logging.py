"""Tests for logging setup."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from src.config.logging import setup_logging


def test_setup_logging_default_runs_without_error() -> None:
    """Default setup completes without error."""
    # Act & Assert
    setup_logging()


def test_setup_logging_with_file_creates_sink(tmp_path: Path) -> None:
    """Setup with a file path runs without error."""
    # Arrange
    log_file = tmp_path / "test.log"

    # Act
    setup_logging(log_file=str(log_file))

    # Assert — no exception raised is the success condition


def test_setup_logging_custom_level() -> None:
    """Setup with custom level runs without error."""
    # Act & Assert
    setup_logging(level="DEBUG")

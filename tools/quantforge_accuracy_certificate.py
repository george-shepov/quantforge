#!/usr/bin/env python3
"""Run the published QuantForge accuracy certificate from the repository."""

from pathlib import Path
import runpy

runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "docs" / "quantforge_accuracy_certificate.py"),
    run_name="__main__",
)

"""Run the source checkout without installing the package."""

from pathlib import Path

_SOURCE_PACKAGE = Path(__file__).resolve().parents[1] / "src" / "explore"
__path__.append(str(_SOURCE_PACKAGE))

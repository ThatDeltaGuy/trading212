"""Pytest configuration for Trading212 integration tests.

Adds the repository root to sys.path so that `custom_components.trading212`
is importable without installing the package.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Repository root (parent of this tests/ directory)
REPO_ROOT = Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

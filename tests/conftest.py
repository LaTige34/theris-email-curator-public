"""pytest conftest — expose skill root on sys.path (public repo layout)."""

from __future__ import annotations

import sys
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[1]
s = str(_SKILL_ROOT)
if s not in sys.path:
    sys.path.insert(0, s)

#!/usr/bin/env python3
"""Thin wrapper for ops.monitoring.synthetic_bot.

This keeps deployment commands stable while allowing the implementation to live
under ops/monitoring/.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops.monitoring.synthetic_bot import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
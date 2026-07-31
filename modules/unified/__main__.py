"""python -m modules.unified → thin CLI."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parent / "code"
sys.path.insert(0, str(CODE))
sys.argv[0] = str(CODE / "cli.py")
runpy.run_path(str(CODE / "cli.py"), run_name="__main__")

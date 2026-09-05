"""Locate and import the organisers' local scorer, veckit (https://github.com/aristoteleo/veckit).

veckit is NOT vendored in this kit. Provide it in one of these ways (checked in this order):

  1. `pip install git+https://github.com/aristoteleo/veckit.git` (or `pip install -e <clone>`): the module
     `score_h5ad` is then importable directly;
  2. set the environment variable VECKIT_PATH to the directory of a clone (the one containing score_h5ad.py);
  3. clone it into <kit>/third_party/veckit.

`load_veckit()` returns the `score_h5ad` module; `veckit_available()` says whether that would succeed.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parents[1]
INSTALL_HINT = ("veckit not found. Install it with `pip install git+https://github.com/aristoteleo/veckit.git`, or set "
                "VECKIT_PATH to a clone directory containing score_h5ad.py, or clone it into third_party/veckit.")


def candidate_dirs() -> list:
    out = []
    env = os.environ.get("VECKIT_PATH")
    if env:
        out.append(Path(env))
    out.append(KIT_ROOT / "third_party" / "veckit")
    return out


def veckit_dir():
    """The directory veckit would be loaded from (None when it is only available as an installed module)."""
    for d in candidate_dirs():
        if (d / "score_h5ad.py").exists():
            return d
    return None


def load_veckit():
    """Import and return veckit's `score_h5ad` module (raises ImportError with installation instructions)."""
    if "score_h5ad" in sys.modules:
        return sys.modules["score_h5ad"]
    d = veckit_dir()
    if d is not None and str(d) not in sys.path:
        sys.path.insert(0, str(d))
    try:
        return importlib.import_module("score_h5ad")
    except ImportError as e:
        raise ImportError(INSTALL_HINT + f" (import error: {e})") from e


def veckit_available() -> bool:
    try:
        load_veckit()
        return True
    except ImportError:
        return False

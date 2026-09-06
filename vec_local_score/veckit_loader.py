"""Locate and import the organisers' local scorer, veckit (https://github.com/aristoteleo/veckit).

veckit is NOT vendored in this kit. Obtain it from the organisers and provide it in one of these ways (checked
in this order):

  1. `pip install git+https://github.com/aristoteleo/veckit.git@46d41e63f42a9aab815db20b742feeccd249cb17` (or `pip install -e <clone>`): the module
     `score_h5ad` is then importable directly;
  2. set the environment variable VECKIT_PATH to the directory of a clone (the one containing score_h5ad.py);
  3. clone it into <kit>/third_party/veckit.

veckit needs numpy, scipy, anndata and scikit-learn.

`load_veckit()` returns the `score_h5ad` module; `veckit_available()` says whether that would succeed;
`veckit_info()` reports the version, location and file hashes of the veckit actually loaded. The kit was tested
against TESTED_VECKIT_VERSION (see below); the organisers' scorer is the source of truth and the wrapper may lag it.
"""
from __future__ import annotations

import hashlib
import importlib
import os
import re
import sys
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parents[1]
INSTALL_HINT = ("veckit not found. Install it with `pip install git+https://github.com/aristoteleo/veckit.git@46d41e63f42a9aab815db20b742feeccd249cb17`, or set "
                "VECKIT_PATH to a clone directory containing score_h5ad.py, or clone it into third_party/veckit.")

# The veckit the kit was developed and tested against (pyproject.toml version; git commit of the clone).
TESTED_VECKIT_VERSION = "0.1.1"
TESTED_VECKIT_COMMIT = "46d41e63f42a9aab815db20b742feeccd249cb17"
TESTED_VECKIT_SHA256 = {
    "score_h5ad.py": "9460f191d49cdcab2100ceb068759f4d6ea49570174c23846193c59f175f404d",
    "common/core_metrics.py": "e06dc84ecd8723ecacb1f31a0f4deb9a8722d37ff90193a7af05e2405fefb5e9",
}


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


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def veckit_info() -> dict:
    """Version, location and file hashes of the veckit actually loaded, plus whether they match the tested one."""
    sh = load_veckit()
    mod_path = Path(getattr(sh, "__file__", "") or "")
    root = mod_path.parent if mod_path.name else None
    info = {"module": str(mod_path) if mod_path.name else None, "root": str(root) if root else None,
            "version": None, "sha256": {}, "matches_tested": None}
    if root is not None:
        pj = root / "pyproject.toml"
        if pj.exists():
            m = re.search(r'^version\s*=\s*"([^"]+)"', pj.read_text(encoding="utf-8"), re.M)
            if m:
                info["version"] = m.group(1)
        for rel in TESTED_VECKIT_SHA256:
            f = root / rel
            if f.exists():
                info["sha256"][rel] = _sha256(f)
    if info["version"] is None:
        try:
            from importlib.metadata import version
            info["version"] = version("veckit")
        except Exception:  # noqa: BLE001 - metadata is optional information
            pass
    if info["sha256"]:
        info["matches_tested"] = all(info["sha256"].get(k) == v for k, v in TESTED_VECKIT_SHA256.items())
    return info

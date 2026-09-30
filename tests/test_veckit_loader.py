"""veckit_loader without veckit: the tested-veckit file hashes do not depend on line endings."""
from __future__ import annotations

import hashlib

from vec_local_score import veckit_loader as vl


def test_sha256_is_line_ending_independent(tmp_path):
    """A Windows checkout (git core.autocrlf writes CRLF) and a Linux pip install (LF) of the same veckit commit
    must hash the same, or veckit_info() reports matches_tested=False for the tested commit."""
    lf, crlf = tmp_path / "lf.py", tmp_path / "crlf.py"
    lf.write_bytes(b"a = 1\nb = '\\r'\n")
    crlf.write_bytes(b"a = 1\r\nb = '\\r'\r\n")
    want = hashlib.sha256(b"a = 1\nb = '\\r'\n").hexdigest()
    assert vl._sha256(lf) == want
    assert vl._sha256(crlf) == want


def test_tested_hashes_are_lf_hashes_of_the_pinned_commit():
    """The recorded hashes are those of the files as stored at the pinned commit (LF), checked against the values
    published by the upstream repository at 46d41e63 (raw.githubusercontent.com, read 2026-09-30)."""
    assert vl.TESTED_VECKIT_COMMIT == "46d41e63f42a9aab815db20b742feeccd249cb17"
    assert vl.TESTED_VECKIT_SHA256 == {
        "score_h5ad.py": "52034554f03aec10193cb09baa2c78a1de04218ef678f327eb63acc58fa28add",
        "common/core_metrics.py": "3be7099a0c9a7ad5b609f86078871ed8290ed0bd8916b0cb3e14fb9831909f31",
    }


def test_veckit_info_matches_tested_on_a_crlf_copy(tmp_path, monkeypatch):
    """veckit_info() on a directory whose files hash (after CRLF -> LF) to the tested values says matches_tested."""
    root = tmp_path / "veckit"
    (root / "common").mkdir(parents=True)
    body = {"score_h5ad.py": b"x = 1\n", "common/core_metrics.py": b"y = 2\n"}
    for rel, data in body.items():
        (root / rel).write_bytes(data.replace(b"\n", b"\r\n"))
    (root / "pyproject.toml").write_text('[project]\nname = "veckit"\nversion = "0.1.1"\n', encoding="utf-8")

    class FakeModule:
        __file__ = str(root / "score_h5ad.py")

    monkeypatch.setattr(vl, "load_veckit", lambda: FakeModule)
    monkeypatch.setattr(vl, "TESTED_VECKIT_SHA256", {k: hashlib.sha256(v).hexdigest() for k, v in body.items()})
    info = vl.veckit_info()
    assert info["version"] == "0.1.1"
    assert info["matches_tested"] is True
    (root / "common" / "core_metrics.py").write_bytes(b"y = 3\r\n")
    assert vl.veckit_info()["matches_tested"] is False

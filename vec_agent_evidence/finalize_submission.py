#!/usr/bin/env python
"""Finalize a candidate prediction as the submission of this run - the ONLY sanctioned route into submission/.

  python tools/finalize_submission.py --board T3:gata4 --candidate out/candidates/c3/pred.h5ad [--candidate-id c3] [--note "..."]

Steps
  1. validate the candidate with vec_submit_check.check (the candidate is never modified);
  2. copy it to a temporary file inside $VEC_RUN_DIR/submission/ and verify the copy's sha256 equals the
     candidate's sha256;
  3. atomic os.replace onto submission/pred_<board-sanitised>.h5ad (T3:gata4 -> pred_T3_gata4.h5ad);
  4. append {board, candidate, sha256, bytes, utc, ...} to submission/MANIFEST.json.
--relax-cells skips ONLY the min_cells check and is honoured only when VEC_ALLOW_RELAX=1 (dry runs on tiny
sample files); a relaxed file is never uploadable and is flagged in the manifest.
Exit 0 = finalized; 1 = refused (nothing changed); 2 = usage error.

This file is copied into <run>/workspace/tools/ next to the vec_* packages; it also works from the kit root.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _cand in (HERE, HERE.parent):
    if (_cand / "vec_submit_check").is_dir():
        if str(_cand) not in sys.path:
            sys.path.insert(0, str(_cand))
        break

from vec_submit_check import check as check_file  # noqa: E402


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def board_sanitised(board: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", board)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_manifest(path: Path) -> dict:
    if path.exists():
        try:
            m = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(m, dict) and isinstance(m.get("entries"), list):
                return m
        except ValueError:
            pass
        return {"entries": [], "note": "previous MANIFEST.json was unparseable and was replaced"}
    return {"entries": []}


def finalize(candidate: Path, board: str, submission_dir: Path, candidate_id=None, note=None,
             relax_cells: bool = False) -> dict:
    """Programmatic entry point; raises SystemExit(1) on refusal. Returns the manifest entry."""
    candidate = Path(candidate)
    if not candidate.exists():
        raise SystemExit(f"refused: candidate does not exist: {candidate}")
    if relax_cells and os.environ.get("VEC_ALLOW_RELAX") != "1":
        raise SystemExit("refused: --relax-cells is only honoured when VEC_ALLOW_RELAX=1 (dry runs); a real submission "
                         "must satisfy min_cells")
    rep = check_file(candidate, board)
    errors = list(rep["errors"])
    ignored = []
    if relax_cells:
        ignored = [e for e in errors if "< min_cells" in e]
        errors = [e for e in errors if "< min_cells" not in e]
    if errors:
        raise SystemExit(f"refused: {candidate} fails the {board} contract:\n  " + "\n  ".join(errors))

    submission_dir.mkdir(parents=True, exist_ok=True)
    final = submission_dir / f"pred_{board_sanitised(board)}.h5ad"
    tmp = submission_dir / f".{final.stem}.{os.getpid()}.tmp"
    src_sha = sha256_file(candidate)
    try:
        shutil.copyfile(candidate, tmp)
        if sha256_file(tmp) != src_sha:
            raise SystemExit("refused: copy verification failed (sha256 differs)")
        os.replace(tmp, final)
    finally:
        if tmp.exists():
            tmp.unlink()
    entry = {
        "board": board, "candidate": candidate_id or candidate.parent.name, "candidate_path": str(candidate),
        "file": final.name, "sha256": src_sha, "bytes": final.stat().st_size, "utc": utc_now(),
        "note": note, "relaxed_min_cells": bool(ignored), "uploadable": not ignored,
        "n_obs": rep["info"].get("n_obs"), "n_vars": rep["info"].get("n_vars"),
        "checker_warnings": rep["warnings"], "finalize_tool_sha256": sha256_file(Path(__file__)),
    }
    mpath = submission_dir / "MANIFEST.json"
    m = load_manifest(mpath)
    m["entries"].append(entry)
    m["updated_utc"] = entry["utc"]
    mtmp = submission_dir / f".MANIFEST.{os.getpid()}.tmp"
    mtmp.write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")
    os.replace(mtmp, mpath)
    return entry


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="backslashreplace")
            except (ValueError, AttributeError):
                pass
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--board", required=True, help="index.json key, e.g. T3:gata4, T2:heart:val_extrap")
    p.add_argument("--candidate", required=True, type=Path, help="candidate .h5ad (left unchanged)")
    p.add_argument("--candidate-id", default=None, help="candidate label (default: parent directory name)")
    p.add_argument("--note", default=None)
    p.add_argument("--relax-cells", action="store_true", help="skip only the min_cells check (VEC_ALLOW_RELAX=1 only)")
    p.add_argument("--submission-dir", type=Path, default=None,
                   help="default $VEC_RUN_DIR/submission (set by the harness); explicit path for tests")
    args = p.parse_args(argv)
    sub = args.submission_dir
    if sub is None:
        run_dir = os.environ.get("VEC_RUN_DIR")
        if not run_dir:
            print("usage error: VEC_RUN_DIR is not set and --submission-dir was not given", file=sys.stderr)
            return 2
        sub = Path(run_dir) / "submission"
    try:
        entry = finalize(args.candidate, args.board, sub, args.candidate_id, args.note, args.relax_cells)
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 1 if str(e).startswith("refused") else 2
    except KeyError as e:
        print(f"usage error: {e}", file=sys.stderr)
        return 2
    print(f"[FINALIZED] {entry['file']} board={entry['board']} candidate={entry['candidate']} sha256={entry['sha256']} "
          f"bytes={entry['bytes']} n_obs={entry['n_obs']} relaxed={entry['relaxed_min_cells']}")
    for w in entry["checker_warnings"]:
        print(f"  warn : {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

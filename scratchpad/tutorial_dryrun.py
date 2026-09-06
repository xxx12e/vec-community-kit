"""Scratchpad (not committed): run the tutorials' commands verbatim against tiny synthetic stages.

Plants synthetic files under the kit's gitignored data/raw/ layout used by docs/tutorial_*.md, runs every
`python -m ...` command of the tutorials from the kit root exactly as written (relative paths), and prints rc +
head of the output. `--clean` removes the planted files afterwards.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import scipy.sparse as sp
import anndata as ad
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from conftest import make_adata  # noqa: E402
from vec_submit_check import panel_for_board  # noqa: E402

PY = sys.executable
RAW = ROOT / "data" / "raw"
OUT = ROOT / "out"
UP, DOWN = list(range(20, 45)), list(range(300, 320))


def heart_stage(panel, n, seed, changed=False, coord_scale=1.0):
    a = make_adata(panel, n, seed=seed, density=0.4)
    X = np.asarray(a.X)
    X[:, DOWN] += 2.0
    if changed:
        eff = np.random.default_rng(123)
        X[:, UP] += eff.uniform(0.4, 2.5, size=len(UP))
        X[:, DOWN] = np.maximum(X[:, DOWN] - eff.uniform(0.5, 1.8, size=len(DOWN)), 0.0)
    a.X = X.astype(np.float32)
    a.obsm["spatial_3D"] = (np.asarray(a.obsm["spatial_3D"]) * coord_scale).astype(np.float32)
    return a


def t1_stage(panel, n, seed, changed=False):
    rng = np.random.default_rng(seed)
    X = sp.random(n, len(panel), density=0.004, format="csr", dtype=np.float32, random_state=seed)
    X.data = (np.abs(X.data) * 3).astype(np.float32)
    X = X.tolil()
    ct = rng.choice(["A", "B", "C"], size=n)
    for i, t in enumerate(("A", "B", "C")):
        X[np.flatnonzero(ct == t), i * 7:i * 7 + 5] = 1.5
    X[:, 1000:1020] = 2.0
    if changed:
        eff = np.random.default_rng(7)
        X[:, 500:525] = np.asarray(X[:, 500:525].todense()) + eff.uniform(0.4, 2.5, size=25)
        X[:, 1000:1020] = np.maximum(np.asarray(X[:, 1000:1020].todense()) - eff.uniform(0.5, 1.8, size=20), 0.0)
    obs = pd.DataFrame({"celltype": pd.Categorical(ct)}, index=pd.Index([f"c{i}" for i in range(n)]))
    return ad.AnnData(X=sp.csr_matrix(X, dtype=np.float32), obs=obs, var=pd.DataFrame(index=pd.Index(panel)))


def plant():
    heart = panel_for_board("T3:gata4")[1]
    t1 = panel_for_board("T1:val")[1]
    (RAW / "T1").mkdir(parents=True, exist_ok=True)
    (RAW / "T2_heart").mkdir(parents=True, exist_ok=True)
    (RAW / "T2_embryo").mkdir(parents=True, exist_ok=True)
    t1_stage(t1, 1100, 1).write_h5ad(RAW / "T1" / "E8.5_RNA.h5ad")
    t1_stage(t1, 1100, 2, changed=True).write_h5ad(RAW / "T1" / "E9.5_RNA.h5ad")
    heart_stage(heart, 2400, 21).write_h5ad(RAW / "T2_heart" / "E8.25_late.h5ad")
    heart_stage(heart, 2400, 22, changed=True, coord_scale=1.25).write_h5ad(RAW / "T2_heart" / "E8.75.h5ad")
    heart_stage(heart, 2400, 23, changed=True, coord_scale=1.5).write_h5ad(RAW / "T2_heart" / "E9.5.h5ad")
    heart_stage(heart, 1500, 24).write_h5ad(RAW / "T2_embryo" / "E8.0.h5ad")
    print("planted synthetic stages under", RAW)


def run(cmd: str, timeout=1800):
    print("\n$ " + cmd)
    t0 = time.time()
    env = dict(os.environ, PYTHONUTF8="1")
    r = subprocess.run(cmd, shell=True, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env, timeout=timeout)
    out = (r.stdout + ("\n[stderr]\n" + r.stderr if r.stderr.strip() else "")).strip()
    lines = out.splitlines()
    shown = lines if len(lines) <= 40 else lines[:25] + ["  ..."] + lines[-12:]
    print("\n".join("  " + x for x in shown))
    print(f"  -> rc={r.returncode} ({time.time() - t0:.1f}s)")
    return r.returncode, r.stdout, r.stderr


def main():
    if "--clean" in sys.argv:
        for p in (RAW, OUT, ROOT / "pseudo"):
            shutil.rmtree(p, ignore_errors=True)
        print("cleaned")
        return 0
    plant()
    OUT.mkdir(exist_ok=True)
    rcs = {}
    # section 3
    rcs["pytest"] = run(f'"{PY}" -m pytest -q')[0]
    # section 5 (the tutorial's five baseline commands)
    rcs["t1"] = run(f'"{PY}" -m vec_baselines.make_baseline --method copy_last   --board T1:val               --last data/raw/T1/E9.5_RNA.h5ad          --out out/t1_copy_last.h5ad --n-cells 5000')[0]
    rcs["embryo"] = run(f'"{PY}" -m vec_baselines.make_baseline --method copy_last   --board T2:embryo:val_interp --last data/raw/T2_embryo/E8.0.h5ad       --out out/embryo_copy_last.h5ad --n-cells 5000')[0]
    rcs["hi"] = run(f'"{PY}" -m vec_baselines.make_baseline --method copy_last   --board T2:heart:val_interp  --last data/raw/T2_heart/E8.25_late.h5ad  --out out/heart_interp_copy_last.h5ad --n-cells 5000')[0]
    rcs["he"] = run(f'"{PY}" -m vec_baselines.make_baseline --method copy_last   --board T2:heart:val_extrap  --last data/raw/T2_heart/E9.5.h5ad        --out out/heart_extrap_copy_last.h5ad --n-cells 5000')[0]
    rcs["t3"] = run(f'"{PY}" -m vec_baselines.make_baseline --method wt_identity --board T3:gata4             --wt   data/raw/T2_heart/E8.75.h5ad       --out out/t3_wt_identity.h5ad --n-cells 5000')[0]
    rcs["py_api"] = run(f'"{PY}" -c "from vec_baselines import io as bio, methods as bm; spec, panel = bio.panel_for_board(\'T3:gata4\'); wt = bio.load_stage(\'data/raw/T2_heart/E8.75.h5ad\', panel); X, C, info = bm.wt_identity(wt); report = bio.write_submission(X, C, panel, \'out/t3_wt_identity_api.h5ad\', \'T3:gata4\', n_cells=2000); print(report[\'ok\'], report[\'info\'][\'n_obs\'])"')[0]
    # section 6
    rcs["check1"] = run(f'"{PY}" -m vec_submit_check --board T2:heart:val_interp out/heart_interp_copy_last.h5ad')[0]
    rcs["check2"] = run(f'"{PY}" -m vec_submit_check --board T1:val out/t1_copy_last.h5ad --json out/t1_check.json')[0]
    # section 7
    rcs["avail"] = run(f'"{PY}" -c "from vec_local_score import veckit_available, veckit_info; print(veckit_available(), veckit_info())"')[0]
    rcs["pseudo_pred"] = run(f'"{PY}" -m vec_baselines.make_baseline --method copy_last --board T2:heart:val_interp --last data/raw/T2_heart/E8.25_late.h5ad --out out/pseudo_pred.h5ad --n-cells 5000')[0]
    rcs["ls_t2"] = run(f'"{PY}" -m vec_local_score --task T2 --setting heart --pred out/pseudo_pred.h5ad --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad --frac 0.1 --seed 0')[0]
    rcs["ss_t2"] = run(f'"{PY}" -m vec_local_score.seed_summary --task T2 --setting heart --pred out/pseudo_pred.h5ad --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad --seeds 0 1 2 3 4')[0]
    rcs["ls_t1"] = run(f'"{PY}" -m vec_local_score --task T1 --pred out/t1_copy_last.h5ad --target data/raw/T1/E9.5_RNA.h5ad --reference data/raw/T1/E8.5_RNA.h5ad')[0]
    rcs["ls_t3"] = run(f'"{PY}" -m vec_local_score --task T3 --pred out/t3_wt_identity.h5ad --target data/raw/T2_heart/E8.75.h5ad --wt data/raw/T2_heart/E8.25_late.h5ad')[0]
    rcs["split"] = run(f'"{PY}" -m vec_local_score.make_pseudo_split --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad --out-dir pseudo/heart --panel data/panels/T2__heart__val_interp.genes.txt --require-coords')[0]
    rcs["split_refused"] = run(f'"{PY}" -m vec_local_score --task T2 --setting heart --pred out/pseudo_pred.h5ad --target pseudo/heart/target_score.h5ad --reference pseudo/heart/reference.h5ad')[0]
    # section 9
    rcs["evidence_tests"] = run(f'"{PY}" -m pytest tests/test_evidence.py -q')[0]
    rcs["lock"] = run(f'"{PY}" -m vec_agent_evidence lock --task T3 --prompt vec_agent_evidence/example_prompt.md --model claude-opus-5 --data-root ./data --hours 8 --runs-root scratchpad/runs_dryrun')[0]
    print("\nSUMMARY", json.dumps(rcs, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

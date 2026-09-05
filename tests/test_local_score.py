"""vec_local_score against the organisers' veckit on synthetic data. Skipped when veckit is not available
(install it or set VECKIT_PATH; see vec_local_score/README.md)."""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
import pytest

from vec_local_score import TESTED_VECKIT_VERSION, veckit_available, veckit_info
from vec_local_score.local_score import (DIRECTION, GROUPS, WEIGHTS, format_table, main as ls_main, score, skill,
                                         skill_hyperbolic, veckit_skill_fn)
from vec_local_score.make_pseudo_split import MARKER, make_split
from vec_local_score.seed_summary import format_summary, summarise

from conftest import make_adata

pytestmark = pytest.mark.skipif(not veckit_available(), reason="veckit not installed and VECKIT_PATH not set")

ROOT = Path(__file__).resolve().parents[1]
G = 200
GENES = [f"g{i:03d}" for i in range(G)]


def make_stage(seed, n, shift=None, types=("A", "B", "C")):
    rng = np.random.default_rng(seed)
    X = rng.gamma(0.6, 1.0, size=(n, G))
    X[rng.random((n, G)) >= 0.5] = 0.0
    ct = rng.choice(list(types), size=n)
    for i, t in enumerate(types):
        X[ct == t, i * 10:(i + 1) * 10] += 2.0
    if shift is not None:
        X = X + shift
    X = np.clip(X, 0, None).astype(np.float32)
    obs = pd.DataFrame({"celltype": pd.Categorical(ct)}, index=pd.Index([f"c{i}" for i in range(n)]))
    return ad.AnnData(X=X, obs=obs, var=pd.DataFrame(index=pd.Index(GENES)))


@pytest.fixture(scope="module")
def t1_files(tmp_path_factory):
    d = tmp_path_factory.mktemp("t1")
    shift = np.zeros(G)
    shift[100:130] = 1.2          # up-regulated in the target
    shift[130:160] = -0.9         # down-regulated in the target
    ref = make_stage(0, 400)
    tgt = make_stage(1, 400, shift)
    ref.write_h5ad(d / "reference.h5ad")
    tgt.write_h5ad(d / "target.h5ad")
    ref.write_h5ad(d / "pred_copy_last.h5ad")   # the floor row: the reference resubmitted
    return d


def test_skill_map():
    # higher is better
    assert skill(0.5, 0.0, 1.0, +1) == pytest.approx(2 / 3) and skill(0.0, 0.0, 1.0, +1) == 0.5 and skill(1.0, 0.0, 1.0, +1) == 1.0
    assert skill(2.0, 0.0, 1.0, +1) == 1.0                       # better than the ceiling is clipped
    # lower is better
    assert skill(0.1, 0.1, 0.0, -1) == 0.5 and skill(0.0, 0.1, 0.0, -1) == 1.0 and skill(0.3, 0.1, 0.0, -1) == pytest.approx(0.25)
    # target 0: |value| for prediction, floor and ceiling, then lower is better
    assert skill(-0.2, -0.2, 0.0, 0) == 0.5 and skill(0.2, -0.2, 0.0, 0) == 0.5 and skill(0.0, -0.2, 0.0, 0) == 1.0
    assert skill(0.1, -0.2, 0.05, 0) == pytest.approx(0.15 / (0.15 + 0.05))   # |0.1| vs |0.05| ceiling, |-0.2| floor
    assert skill(-0.03, -0.2, 0.05, 0) == 1.0                                # closer to 0 than the ceiling: clipped
    assert skill(1.0, -6.9078, 0.0, 0) == skill(-1.0, -6.9078, 0.0, 0)       # overshoot and undershoot alike
    # missing metric or missing reference values -> 0
    assert skill(None, 0.0, 1.0, +1) == 0.0 and skill(float("nan"), 0.0, 1.0, +1) == 0.0 and skill(0.5, None, 1.0, +1) == 0.0
    # degenerate floor == ceiling
    assert skill(0.0, 0.0, 0.0, +1) == 1.0 and skill(-1.0, 0.0, 0.0, +1) == 0.0
    for task, w in WEIGHTS.items():
        assert sum(w.values()) == pytest.approx(1.0)
        assert set(w) == {m for ms in GROUPS[task].values() for m in ms} <= set(DIRECTION)
    assert DIRECTION["scale_log_ratio"] == 0 and DIRECTION["severity_slope"] == 0


def test_skill_follows_veckit_skill():
    """The wrapper's skill is veckit's common.core_metrics.skill (plus the fold and the two edge-case policies)."""
    from vec_local_score.veckit_loader import load_veckit
    load_veckit()._load_task_metrics("T1")
    vk = veckit_skill_fn()
    assert vk is not None, "veckit's common.core_metrics.skill not importable after loading the metric modules"
    grid = [-3.0, -0.5, -0.1, 0.0, 0.05, 0.2, 0.7, 1.0, 2.5]
    for value in grid:
        for floor in grid:
            for ceiling in grid:
                for lower in (False, True):
                    a, b = vk(value, floor, ceiling, lower), skill_hyperbolic(value, floor, ceiling, lower)
                    assert (math.isnan(a) and math.isnan(b)) or a == pytest.approx(b), (value, floor, ceiling, lower)
                    if abs(floor - ceiling) >= 1e-12:
                        d = -1 if lower else +1
                        assert skill(value, floor, ceiling, d, vk) == pytest.approx(a)
                if abs(abs(floor) - abs(ceiling)) >= 1e-12:
                    assert skill(value, floor, ceiling, 0, vk) == pytest.approx(vk(abs(value), abs(floor), abs(ceiling), True))
    info = veckit_info()
    assert info["version"] and isinstance(info["sha256"], dict)


def test_copy_last_scores_the_floor(t1_files):
    res = score("T1", t1_files / "pred_copy_last.h5ad", t1_files / "target.h5ad", t1_files / "reference.h5ad", frac=1.0, seed=0)
    assert res["cells"] == {"pred": 400, "target_A": 200, "target_B": 200, "reference": 400}
    assert {r["metric"] for r in res["rows"]} == set(WEIGHTS["T1"])
    degenerate = []
    for r in res["rows"]:
        assert r["raw"] is not None and r["floor"] is not None and r["ceiling"] is not None, r
        assert r["raw"] == pytest.approx(r["floor"], rel=1e-9, abs=1e-12), r      # pred IS the reference
        s = skill(r["floor"], r["floor"], r["ceiling"], DIRECTION[r["metric"]])
        assert r["skill"] == pytest.approx(s, abs=1e-4)
        if s != 0.5:
            degenerate.append(r["metric"])
        assert r["folded"] is False and r["degenerate"] is False and r["undefined"] is False
    assert degenerate == [], degenerate            # the synthetic target has real change: every ceiling beats the floor
    # frac=1.0 and pred == reference: the local floor row IS the prediction, so this special case lands on 50.0
    assert res["task_score"] == pytest.approx(50.0, abs=0.01)
    assert res["veckit"]["skill_source"] == "veckit common.core_metrics.skill"
    assert res["veckit"]["tested_against"] == TESTED_VECKIT_VERSION
    txt = format_table(res)
    assert "TASK SCORE" in txt and "de_score" in txt and "veckit" in txt


def test_seed_summary_and_json(t1_files, tmp_path, capsys):
    res = summarise("T1", t1_files / "pred_copy_last.h5ad", t1_files / "target.h5ad", t1_files / "reference.h5ad",
                    seeds=(0, 1), frac=1.0)
    assert res["seeds"] == [0, 1] and len(res["per_seed"]) == 2 and len(res["task_scores"]) == 2
    assert res["task_score_sd"] >= 0 and set(res["metrics"]) == set(WEIGHTS["T1"])
    for m, v in res["metrics"].items():
        assert v["raw_mean"] == pytest.approx(v["floor_mean"], rel=1e-6, abs=1e-9)   # frac=1.0: pred IS the reference
    assert res["task_score_mean"] == pytest.approx(50.0, abs=0.01) and res["veckit"]["version"]
    assert "+-" in format_summary(res)
    # with a real subsample the reference and the prediction differ, so raw moves away from the floor; it still runs
    sub = summarise("T1", t1_files / "pred_copy_last.h5ad", t1_files / "target.h5ad", t1_files / "reference.h5ad",
                    seeds=(0,), frac=0.8)
    assert np.isfinite(sub["task_score_mean"]) and sub["per_seed"][0]["cells"]["reference"] == 320
    out = tmp_path / "ls.json"
    rc = ls_main(["--task", "T1", "--pred", str(t1_files / "pred_copy_last.h5ad"), "--target", str(t1_files / "target.h5ad"),
                  "--reference", str(t1_files / "reference.h5ad"), "--frac", "1.0", "--json", str(out)])
    assert rc == 0 and json.loads(out.read_text(encoding="utf-8"))["task_score"] == pytest.approx(50.0, abs=0.01)
    assert "TASK SCORE" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        ls_main(["--task", "T1", "--pred", str(t1_files / "pred_copy_last.h5ad"), "--target", str(t1_files / "target.h5ad")])


def test_negative_prediction_is_rejected(t1_files, tmp_path):
    a = ad.read_h5ad(t1_files / "pred_copy_last.h5ad")
    a.X[0, 0] = -1.0
    a.write_h5ad(tmp_path / "neg.h5ad")
    with pytest.raises(ValueError, match="negative"):
        score("T1", tmp_path / "neg.h5ad", t1_files / "target.h5ad", t1_files / "reference.h5ad", frac=1.0)
    rc = ls_main(["--task", "T1", "--pred", str(tmp_path / "neg.h5ad"), "--target", str(t1_files / "target.h5ad"),
                  "--reference", str(t1_files / "reference.h5ad"), "--frac", "1.0"])
    assert rc == 1


def test_make_pseudo_split_exports_marked_files_that_the_wrapper_refuses(t1_files, tmp_path):
    meta = make_split(t1_files / "target.h5ad", t1_files / "reference.h5ad", tmp_path / "split", frac=0.5, seed=0)
    assert meta["target_score_cells"] == 100 and meta["target_ceiling_cells"] == 100 and meta["reference_cells"] == 200
    assert meta["genes"] == G and meta["has_coords"] is False and "not an input to vec_local_score" in meta["note"]
    for f in ("target_score.h5ad", "target_ceiling.h5ad", "reference.h5ad", "meta.json"):
        assert (tmp_path / "split" / f).exists()
    a = ad.read_h5ad(tmp_path / "split" / "target_score.h5ad")
    assert list(a.var_names) == GENES and "celltype" in a.obs and a.n_obs == 100
    assert a.uns[MARKER]["role"] == "target_score" and a.uns[MARKER]["tool"] == "vec_local_score.make_pseudo_split"
    # the exported files are for inspection / the veckit CLI; the wrapper refuses them (it would subsample twice)
    with pytest.raises(ValueError, match="make_pseudo_split"):
        score("T1", t1_files / "pred_copy_last.h5ad", tmp_path / "split" / "target_score.h5ad",
              tmp_path / "split" / "reference.h5ad", frac=1.0)
    with pytest.raises(ValueError, match="make_pseudo_split"):
        score("T1", tmp_path / "split" / "reference.h5ad", t1_files / "target.h5ad", t1_files / "reference.h5ad", frac=1.0)
    with pytest.raises(KeyError):
        make_split(t1_files / "target.h5ad", t1_files / "reference.h5ad", tmp_path / "split2", require_coords=True)
    with pytest.raises(ValueError):
        make_split(t1_files / "target.h5ad", t1_files / "reference.h5ad", tmp_path / "split3", panel=GENES + ["nope"])


# ----------------------------------------------------------------------------- the tutorial's section 7, as written
UP_GENES, DOWN_GENES = list(range(20, 45)), list(range(300, 320))


def heart_stage(panel, n, seed, changed=False, coord_scale=1.0):
    """A synthetic heart-like stage on the real 500-gene panel: labels, coordinates, and (when `changed`) a set of
    genes moved up / down by gene-specific amounts, so the DE metrics have heterogeneous fold changes to work with."""
    a = make_adata(panel, n, seed=seed, density=0.4)
    X = np.asarray(a.X)
    X[:, DOWN_GENES] += 2.0                                  # highly expressed in both stages
    if changed:
        eff = np.random.default_rng(123)                     # the same per-gene effect sizes for every call
        X[:, UP_GENES] += eff.uniform(0.4, 2.5, size=len(UP_GENES))
        X[:, DOWN_GENES] = np.maximum(X[:, DOWN_GENES] - eff.uniform(0.5, 1.8, size=len(DOWN_GENES)), 0.0)
    a.X = X.astype(np.float32)
    a.obsm["spatial_3D"] = (np.asarray(a.obsm["spatial_3D"]) * coord_scale).astype(np.float32)
    return a


def run_cli(args, cwd):
    """Run a documented `python -m ...` command exactly as the tutorial does (from the kit root)."""
    env = dict(os.environ, PYTHONUTF8="1")
    r = subprocess.run([sys.executable, "-m", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env, timeout=1800)
    return r.returncode, r.stdout, r.stderr


def test_tutorial_local_scoring_commands_end_to_end(tmp_path, heart_panel):
    """docs/tutorial_*.md section 7 on a tiny synthetic pair of heart stages: baseline -> vec_local_score ->
    seed_summary, each run as a subprocess with the tutorial's flags (only the paths differ)."""
    raw = tmp_path / "data" / "raw" / "T2_heart"
    raw.mkdir(parents=True)
    heart_stage(heart_panel, 2400, seed=21).write_h5ad(raw / "E8.25_late.h5ad")
    heart_stage(heart_panel, 2400, seed=22, changed=True, coord_scale=1.25).write_h5ad(raw / "E8.75.h5ad")
    out = tmp_path / "out"
    out.mkdir()

    rc, so, se = run_cli(["vec_baselines.make_baseline", "--method", "copy_last", "--board", "T2:heart:val_interp",
                          "--last", str(raw / "E8.25_late.h5ad"), "--out", str(out / "pseudo_pred.h5ad"), "--n-cells", "5000"], ROOT)
    assert rc == 0, se
    assert "[PASS]" in so and "requested but the source has only 2400 cells" in so
    assert ad.read_h5ad(out / "pseudo_pred.h5ad").n_obs == 2400

    rc, so, se = run_cli(["vec_local_score", "--task", "T2", "--setting", "heart", "--pred", str(out / "pseudo_pred.h5ad"),
                          "--target", str(raw / "E8.75.h5ad"), "--reference", str(raw / "E8.25_late.h5ad"),
                          "--frac", "0.1", "--seed", "0", "--json", str(out / "ls.json")], ROOT)
    assert rc == 0, se
    res = json.loads((out / "ls.json").read_text(encoding="utf-8"))
    assert res["cells"] == {"pred": 2400, "target_A": 120, "target_B": 120, "reference": 240}
    assert 0.0 <= res["task_score"] <= 100.0 and {r["metric"] for r in res["rows"]} == set(WEIGHTS["T2"])
    slr = [r for r in res["rows"] if r["metric"] == "scale_log_ratio"][0]
    assert slr["folded"] is True and slr["raw"] is not None and slr["floor"] is not None
    # the coordinates of the target were scaled by 1.25: the copy_last floor row undershoots the size (negative signed
    # log ratio, about log(1/1.25) up to the sampling noise of 120-cell halves) while the ceiling half is near 0
    assert slr["floor"] < -0.1 and abs(slr["ceiling"]) < abs(slr["floor"])
    assert slr["skill"] == pytest.approx(skill(slr["raw"], slr["floor"], slr["ceiling"], 0), abs=1e-4)
    assert "TASK SCORE" in so and "scale_log_ratio*" in so and "veckit" in so

    rc, so, se = run_cli(["vec_local_score.seed_summary", "--task", "T2", "--setting", "heart", "--pred", str(out / "pseudo_pred.h5ad"),
                          "--target", str(raw / "E8.75.h5ad"), "--reference", str(raw / "E8.25_late.h5ad"),
                          "--seeds", "0", "1", "2", "3", "4", "--json", str(out / "summary.json")], ROOT)
    assert rc == 0, se
    summ = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summ["seeds"] == [0, 1, 2, 3, 4] and len(summ["per_seed"]) == 5 and np.isfinite(summ["task_score_mean"])
    assert "+-" in so and summ["veckit"]["version"]

    # T3 on the same files (the tutorial: --task T3 --target <knockout> --wt <matched wild type>); severity_slope is
    # folded and the wt_identity floor row sits at veckit's finite worst case log(1e-3)
    rc, so, se = run_cli(["vec_local_score", "--task", "T3", "--pred", str(out / "pseudo_pred.h5ad"),
                          "--target", str(raw / "E8.75.h5ad"), "--wt", str(raw / "E8.25_late.h5ad"),
                          "--frac", "0.1", "--seed", "0", "--json", str(out / "t3.json")], ROOT)
    assert rc == 0, se
    t3 = json.loads((out / "t3.json").read_text(encoding="utf-8"))
    sev = [r for r in t3["rows"] if r["metric"] == "severity_slope"][0]
    assert sev["folded"] is True and sev["floor"] == pytest.approx(math.log(1e-3), abs=1e-3)
    assert sev["ceiling"] is not None and abs(sev["ceiling"]) < abs(sev["floor"])
    assert "severity_slope*" in so

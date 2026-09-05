"""vec_local_score against the organisers' veckit on synthetic data. Skipped when veckit is not available
(install it or set VECKIT_PATH; see vec_local_score/README.md)."""
from __future__ import annotations

import json

import anndata as ad
import numpy as np
import pandas as pd
import pytest

from vec_local_score import veckit_available
from vec_local_score.local_score import DIRECTION, GROUPS, WEIGHTS, format_table, main as ls_main, score, skill
from vec_local_score.make_pseudo_split import make_split
from vec_local_score.seed_summary import format_summary, summarise

pytestmark = pytest.mark.skipif(not veckit_available(), reason="veckit not installed and VECKIT_PATH not set")

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
    assert skill(0.5, 0.0, 1.0, +1) == pytest.approx(2 / 3) and skill(0.0, 0.0, 1.0, +1) == 0.5 and skill(1.0, 0.0, 1.0, +1) == 1.0
    assert skill(2.0, 0.0, 1.0, +1) == 1.0                       # better than the ceiling is clipped
    assert skill(0.1, 0.1, 0.0, -1) == 0.5 and skill(0.0, 0.1, 0.0, -1) == 1.0 and skill(0.3, 0.1, 0.0, -1) == pytest.approx(0.25)
    assert skill(-0.2, -0.2, 0.0, 0) == 0.5 and skill(0.2, -0.2, 0.0, 0) == 0.5 and skill(0.0, -0.2, 0.0, 0) == 1.0
    assert skill(None, 0.0, 1.0, +1) == 0.0 and skill(float("nan"), 0.0, 1.0, +1) == 0.0
    assert skill(0.0, 0.0, 0.0, +1) == 1.0 and skill(-1.0, 0.0, 0.0, +1) == 0.0   # degenerate floor == ceiling
    for task, w in WEIGHTS.items():
        assert sum(w.values()) == pytest.approx(1.0)
        assert set(w) == {m for ms in GROUPS[task].values() for m in ms} <= set(DIRECTION)


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
    assert degenerate == [], degenerate            # the synthetic target has real change: every ceiling beats the floor
    assert res["task_score"] == pytest.approx(50.0, abs=0.01)
    txt = format_table(res)
    assert "TASK SCORE" in txt and "de_score" in txt


def test_seed_summary_and_json(t1_files, tmp_path, capsys):
    res = summarise("T1", t1_files / "pred_copy_last.h5ad", t1_files / "target.h5ad", t1_files / "reference.h5ad",
                    seeds=(0, 1), frac=1.0)
    assert res["seeds"] == [0, 1] and len(res["per_seed"]) == 2 and len(res["task_scores"]) == 2
    assert res["task_score_sd"] >= 0 and set(res["metrics"]) == set(WEIGHTS["T1"])
    for m, v in res["metrics"].items():
        assert v["raw_mean"] == pytest.approx(v["floor_mean"], rel=1e-6, abs=1e-9)   # frac=1.0: pred IS the reference
    assert res["task_score_mean"] == pytest.approx(50.0, abs=0.01)
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


def test_make_pseudo_split(t1_files, tmp_path):
    meta = make_split(t1_files / "target.h5ad", t1_files / "reference.h5ad", tmp_path / "split", frac=0.5, seed=0)
    assert meta["target_score_cells"] == 100 and meta["target_ceiling_cells"] == 100 and meta["reference_cells"] == 200
    assert meta["genes"] == G and meta["has_coords"] is False
    for f in ("target_score.h5ad", "target_ceiling.h5ad", "reference.h5ad", "meta.json"):
        assert (tmp_path / "split" / f).exists()
    a = ad.read_h5ad(tmp_path / "split" / "target_score.h5ad")
    assert list(a.var_names) == GENES and "celltype" in a.obs and a.n_obs == 100
    with pytest.raises(KeyError):
        make_split(t1_files / "target.h5ad", t1_files / "reference.h5ad", tmp_path / "split2", require_coords=True)
    with pytest.raises(ValueError):
        make_split(t1_files / "target.h5ad", t1_files / "reference.h5ad", tmp_path / "split3", panel=GENES + ["nope"])

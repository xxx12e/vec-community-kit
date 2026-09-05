"""vec_baselines on synthetic stages: the three baselines, row selection and the writer (explicit, required n_cells)."""
from __future__ import annotations

import json

import anndata as ad
import numpy as np
import pytest
import scipy.sparse as sp

from vec_baselines import io as bio
from vec_baselines import methods as bm
from vec_baselines.make_baseline import main as make_main
from vec_submit_check import check

from conftest import make_adata


def dense(a):
    return a.X.toarray() if sp.issparse(a.X) else np.asarray(a.X)


def assert_contract(path, board, relaxed=False):
    rep = check(path, board)
    errs = [e for e in rep["errors"] if not (relaxed and "< min_cells" in e)]
    assert errs == [], errs
    spec, panel = bio.panel_for_board(board)
    a = ad.read_h5ad(path)
    assert list(map(str, a.var_names)) == panel
    X = dense(a)
    assert X.dtype == np.float32 and np.all(np.isfinite(X)) and X.min() >= 0
    assert a.n_obs <= spec["max_cells"]
    if spec["needs_coords"]:
        C = np.asarray(a.obsm["spatial_3D"])
        assert C.shape == (a.n_obs, 3) and C.dtype == np.float32 and np.all(np.isfinite(C))
    else:
        assert "spatial_3D" not in a.obsm
    assert "celltype" not in a.obs
    return a


# ----------------------------------------------------------------------------- io
def test_load_stage_reorders_and_rejects_missing(tmp_path, heart_panel):
    a = make_adata(heart_panel, 50, seed=0)
    f = tmp_path / "stage.h5ad"
    a[:, list(reversed(heart_panel))].copy().write_h5ad(f)
    b = bio.load_stage(f, heart_panel)
    assert list(b.var_names) == heart_panel
    with pytest.raises(KeyError):
        bio.load_stage(f, heart_panel + ["NotAGene"])
    with pytest.raises(FileNotFoundError):
        bio.load_stage(tmp_path / "missing.h5ad")


def test_looks_like_counts_and_log_normalize(heart_panel):
    a = make_adata(heart_panel, 40, seed=0)
    assert not bio.looks_like_counts(a.X)
    counts = a.copy()
    counts.X = np.rint(np.expm1(a.X) * 30).astype(np.float32)
    assert bio.looks_like_counts(counts.X)
    b = bio.log_normalize(counts)
    assert not bio.looks_like_counts(b.X) and b.X.dtype == np.float32
    assert np.allclose(np.expm1(dense(b)).sum(1), 1e4, rtol=1e-3)
    counts.X = sp.csr_matrix(counts.X)
    c = bio.log_normalize(counts)
    assert sp.issparse(c.X) and np.allclose(np.expm1(dense(c)).sum(1), 1e4, rtol=1e-3)


def test_parse_n_cells():
    assert bio.parse_n_cells("all") == "all" and bio.parse_n_cells(" ALL ") == "all"
    assert bio.parse_n_cells(5000) == 5000 and bio.parse_n_cells("5000") == 5000 and bio.parse_n_cells(np.int64(7)) == 7
    for bad in (None, True, 2.5, "some", [5000]):
        with pytest.raises(ValueError, match="n_cells is required"):
            bio.parse_n_cells(bad)


def test_select_rows_policies():
    spec = {"min_cells": 1000, "max_cells": 7449}
    # n_cells is required: None raises and the message says what to pass
    with pytest.raises(ValueError, match="n_cells is required.*'all'"):
        bio.select_rows(20000, spec)
    with pytest.raises(ValueError, match="n_cells is required"):
        bio.select_rows(20000, spec, n_cells=None)
    # explicit int inside the bounds: a seeded subset without replacement, sorted
    idx, notes = bio.select_rows(20000, spec, n_cells=4000)
    assert len(idx) == 4000 and len(set(idx)) == 4000 and np.all(np.diff(idx) > 0) and notes["n_cells_mode"] == "explicit"
    assert notes["sampled_without_replacement"] and notes["target"] == 4000
    # explicit int above max_cells is an error that states the bound (never a silent clamp)
    with pytest.raises(ValueError, match=r"exceeds the board's max_cells=7449.*\[1000, 7449\]"):
        bio.select_rows(20000, spec, n_cells=10000)
    # explicit int below min_cells: error unless relaxed
    with pytest.raises(ValueError, match="below the board's min_cells=1000"):
        bio.select_rows(2500, spec, n_cells=500)
    idx, notes = bio.select_rows(150, spec, n_cells="all", relax_cells=True)
    assert np.array_equal(idx, np.arange(150)) and notes["below_min_cells_relaxed"]
    # fewer source rows than requested (but >= min_cells): every row, flagged
    idx, notes = bio.select_rows(2500, spec, n_cells=5000)
    assert np.array_equal(idx, np.arange(2500)) and notes["kept_all_rows"] and notes["n_written"] == 2500
    # below min_cells without relax: duplicates fill up to min_cells
    idx, notes = bio.select_rows(150, spec, n_cells=1000)
    assert len(idx) == 1000 and notes["duplicated_rows"] == 850 and set(idx) == set(range(150))
    # "all": every row, or an error that states the bound
    idx, notes = bio.select_rows(6000, spec, n_cells="all")
    assert np.array_equal(idx, np.arange(6000)) and notes["n_cells_mode"] == "all"
    with pytest.raises(ValueError, match=r"the source has 8000 cells and the board allows at most max_cells=7449.*\[1000, 7449\]"):
        bio.select_rows(8000, spec, n_cells="all")
    with pytest.raises(ValueError):
        bio.select_rows(0, spec, n_cells="all")
    with pytest.raises(ValueError, match="positive"):
        bio.select_rows(2500, spec, n_cells=0)


def test_write_submission_requires_explicit_n_cells(tmp_path, heart_panel):
    a = make_adata(heart_panel, 4500, seed=4, density=0.1)
    X, C, _ = bm.copy_last(a)
    with pytest.raises(ValueError, match="n_cells is required"):
        bio.write_submission(X, C, heart_panel, tmp_path / "none.h5ad", "T3:gata4")
    with pytest.raises(ValueError, match="n_cells is required"):
        bio.write_submission(X, C, heart_panel, tmp_path / "none.h5ad", "T3:gata4", n_cells=None)
    assert not (tmp_path / "none.h5ad").exists()
    rep = bio.write_submission(X, C, heart_panel, tmp_path / "all.h5ad", "T3:gata4", n_cells="all")
    assert rep["info"]["n_obs"] == 4500 and rep["write_info"]["n_cells_mode"] == "all"
    rep = bio.write_submission(X, C, heart_panel, tmp_path / "explicit.h5ad", "T3:gata4", n_cells=1500, seed=3)
    assert rep["info"]["n_obs"] == 1500 and rep["write_info"]["n_cells_mode"] == "explicit"
    assert rep["write_info"]["sampled_without_replacement"]
    assert_contract(tmp_path / "explicit.h5ad", "T3:gata4")
    # a count above the board maximum is refused with the bound, not clamped
    with pytest.raises(ValueError, match="max_cells=7449"):
        bio.write_submission(X, C, heart_panel, tmp_path / "big.h5ad", "T3:gata4", n_cells=8000)
    # "all" on the embryo board (max 5000) with 4500 rows is fine; with 5100 rows it is refused with the bound
    rep = bio.write_submission(X, C, heart_panel, tmp_path / "embryo_all.h5ad", "T2:embryo:val_interp", n_cells="all")
    assert rep["ok"] and rep["info"]["n_obs"] == 4500
    b = make_adata(heart_panel, 5100, seed=5, density=0.05)
    Xb, Cb, _ = bm.copy_last(b)
    with pytest.raises(ValueError, match=r"5100 cells and the board allows at most max_cells=5000.*\[583, 5000\]"):
        bio.write_submission(Xb, Cb, heart_panel, tmp_path / "embryo_big.h5ad", "T2:embryo:val_interp", n_cells="all")
    assert not (tmp_path / "embryo_big.h5ad").exists()


def test_write_submission_clips_maps_columns_and_validates(tmp_path, heart_panel):
    a = make_adata(heart_panel, 1100, seed=5)
    X, C, _ = bm.wt_identity(a)
    X[0, 0] = -1.0
    X[1, 1] = -0.5
    # columns given in reversed order must be mapped back onto the panel
    rep = bio.write_submission(X[:, ::-1], C, list(reversed(heart_panel)), tmp_path / "remap.h5ad", "T3:gata4", n_cells="all")
    assert rep["ok"] and rep["ok_for_upload"] and rep["ignored_errors"] == []
    assert rep["write_info"]["n_negative_clipped"] == 2 and rep["write_info"]["columns_remapped"]
    out = assert_contract(tmp_path / "remap.h5ad", "T3:gata4")
    Xw = dense(out)
    assert Xw[0, 0] == 0.0 and Xw[1, 1] == 0.0
    assert np.allclose(Xw, np.maximum(X, 0))
    assert X[0, 0] == -1.0                                           # the caller's array was not clipped in place
    assert not (tmp_path / "remap.tmp.h5ad").exists()
    with pytest.raises(KeyError):
        bio.write_submission(X[:, :499], C, heart_panel[:499], tmp_path / "x.h5ad", "T3:gata4", n_cells="all")
    with pytest.raises(bio.SubmissionError):
        bio.write_submission(X, None, heart_panel, tmp_path / "y.h5ad", "T3:gata4", n_cells="all")
    Xn = X.copy()
    Xn[2, 2] = np.nan
    with pytest.raises(bio.SubmissionError):
        bio.write_submission(Xn, C, heart_panel, tmp_path / "z.h5ad", "T3:gata4", n_cells="all")
    assert not (tmp_path / "z.h5ad").exists()
    # relaxed tiny file: written, flagged not uploadable
    small = make_adata(heart_panel, 60, seed=6)
    Xs, Cs, _ = bm.wt_identity(small)
    rep = bio.write_submission(Xs, Cs, heart_panel, tmp_path / "small.h5ad", "T3:gata4", relax_cells=True, n_cells="all")
    assert rep["ok"] and not rep["ok_for_upload"] and rep["ignored_errors"]
    assert_contract(tmp_path / "small.h5ad", "T3:gata4", relaxed=True)


def test_write_submission_embryo_board_from_heart_matrix(tmp_path, heart_panel):
    a = make_adata(heart_panel, 1000, seed=8)
    X, C, _ = bm.copy_last(a)
    rep = bio.write_submission(X, C, heart_panel, tmp_path / "embryo.h5ad", "T2:embryo:val_interp", n_cells="all")
    assert rep["ok"]
    out = assert_contract(tmp_path / "embryo.h5ad", "T2:embryo:val_interp")
    assert out.n_vars == 498 and not {"Casp4", "Pnliprp1"} & set(out.var_names)


def test_t1_writer_stores_csr_and_drops_coords(tmp_path):
    spec, panel = bio.panel_for_board("T1:val")
    n = 1000
    X = sp.random(n, len(panel), density=0.003, format="csr", dtype=np.float32, random_state=1)
    X.data = np.abs(X.data) * 2
    coords = np.zeros((n, 3), dtype=np.float32)
    rep = bio.write_submission(X, coords, panel, tmp_path / "t1.h5ad", "T1:val", n_cells="all")
    assert rep["ok"] and rep["info"]["X_format"] == "csr_matrix" and rep["write_info"]["coords_dropped"]
    assert_contract(tmp_path / "t1.h5ad", "T1:val")


# ----------------------------------------------------------------------------- methods
def test_copy_last_and_wt_identity_are_copies(heart_panel):
    a = make_adata(heart_panel, 30, seed=9)
    for fn in (bm.copy_last, bm.wt_identity):
        X, C, info = fn(a)
        assert X.dtype == np.float32 and np.array_equal(X, dense(a)) and info["n_cells"] == 30
        assert C is not None and C.dtype == np.float32 and C.shape == (30, 3)
        assert not np.shares_memory(C, np.asarray(a.obsm["spatial_3D"])) and not np.shares_memory(X, a.X)
        C[0, 0] += 1.0
        assert not np.isclose(C[0, 0], np.asarray(a.obsm["spatial_3D"])[0, 0])
    X, C, _ = bm.copy_last(a, rows=np.array([0, 0, 5]))
    assert X.shape == (3, 500) and np.array_equal(X[0], X[1]) and np.array_equal(X[2], dense(a)[5])
    b = a.copy()
    del b.obsm["spatial_3D"]
    assert bm.copy_last(b)[1] is None


def test_pseudobulk_shift_math(heart_panel):
    prev = make_adata(heart_panel, 300, seed=10, celltypes=("A", "B", "D"))
    last = make_adata(heart_panel, 200, seed=11, celltypes=("A", "B", "C"))
    X, C, info = bm.pseudobulk_shift(prev, last)
    assert X.shape == (200, 500) and X.min() >= 0
    assert np.array_equal(C, np.asarray(last.obsm["spatial_3D"], dtype=np.float32))
    assert info["shared_types"] == ["A", "B"] and set(info["unmatched_types_in_last"]) == {"C"}
    assert info["types_only_in_prev"] == ["D"]
    assert info["n_cells_shifted"] + info["n_cells_unshifted"] == 200
    L, P = dense(last).astype(np.float64), dense(prev).astype(np.float64)
    ct_l = np.asarray(last.obs["celltype"]).astype(str)
    ct_p = np.asarray(prev.obs["celltype"]).astype(str)
    assert np.allclose(X[ct_l == "C"], L[ct_l == "C"])                # unmatched cells copied verbatim
    d = L[ct_l == "A"].mean(0) - P[ct_p == "A"].mean(0)
    assert np.allclose(X[ct_l == "A"], np.maximum(L[ct_l == "A"] + d, 0), atol=1e-5)
    assert info["frac_cells_shifted"] == pytest.approx(np.mean(np.isin(ct_l, ["A", "B"])))
    with pytest.raises(ValueError):
        bm.pseudobulk_shift(prev[:, ::-1].copy(), last)
    with pytest.raises(KeyError):
        bm.pseudobulk_shift(prev, last, celltype_key="nope")


# ----------------------------------------------------------------------------- CLI
def test_cli_copy_last_and_flags(tmp_path, heart_panel, capsys):
    stage = tmp_path / "last.h5ad"
    make_adata(heart_panel, 1300, seed=12).write_h5ad(stage)
    out = tmp_path / "pred.h5ad"
    rc = make_main(["--method", "copy_last", "--board", "T2:heart:val_interp", "--last", str(stage), "--out", str(out),
                    "--n-cells", "all", "--json", str(tmp_path / "rep.json")])
    assert rc == 0
    a = assert_contract(out, "T2:heart:val_interp")
    assert a.n_obs == 1300
    payload = json.loads((tmp_path / "rep.json").read_text(encoding="utf-8"))
    assert payload["check"]["ok"] and payload["info"]["method"] == "copy_last"
    # --n-cells is required: leaving it out is a usage error and nothing is written
    with pytest.raises(SystemExit):
        make_main(["--method", "copy_last", "--board", "T2:heart:val_interp", "--last", str(stage), "--out", str(tmp_path / "def.h5ad")])
    assert not (tmp_path / "def.h5ad").exists()
    capsys.readouterr()
    # a count above what the source holds (but >= min_cells): every source cell is written, with a NOTE
    rc = make_main(["--method", "copy_last", "--board", "T2:heart:val_interp", "--last", str(stage), "--out", str(tmp_path / "req.h5ad"),
                    "--n-cells", "5000"])
    out_text = capsys.readouterr().out
    assert rc == 0 and "requested but the source has only 1300 cells" in out_text
    assert ad.read_h5ad(tmp_path / "req.h5ad").n_obs == 1300
    # "all" above the board maximum fails with the bound in the message (embryo board: max 5000)
    big = tmp_path / "big.h5ad"
    make_adata(heart_panel, 5100, seed=13, density=0.05).write_h5ad(big)
    rc = make_main(["--method", "copy_last", "--board", "T2:embryo:val_interp", "--last", str(big), "--out", str(tmp_path / "all.h5ad"),
                    "--n-cells", "all"])
    err_text = capsys.readouterr().err
    assert rc == 1 and "max_cells=5000" in err_text and not (tmp_path / "all.h5ad").exists()
    # an explicit count above the maximum is refused the same way
    rc = make_main(["--method", "copy_last", "--board", "T2:embryo:val_interp", "--last", str(big), "--out", str(tmp_path / "too.h5ad"),
                    "--n-cells", "6000"])
    assert rc == 1 and "max_cells=5000" in capsys.readouterr().err
    # a count inside the bound works on the 498-gene embryo board from the 500-gene file
    rc = make_main(["--method", "copy_last", "--board", "T2:embryo:val_interp", "--last", str(big), "--out", str(tmp_path / "emb.h5ad"),
                    "--n-cells", "5000"])
    assert rc == 0 and assert_contract(tmp_path / "emb.h5ad", "T2:embryo:val_interp").n_obs == 5000
    capsys.readouterr()
    # count-scale input is refused without --log1p-counts
    counts = tmp_path / "counts.h5ad"
    c = make_adata(heart_panel, 1100, seed=14)
    c.X = np.rint(np.expm1(c.X) * 30).astype(np.float32)
    c.write_h5ad(counts)
    rc = make_main(["--method", "copy_last", "--board", "T3:gata4", "--wt", str(counts), "--last", str(counts), "--out",
                    str(tmp_path / "c.h5ad"), "--n-cells", "all"])
    assert rc == 1 and not (tmp_path / "c.h5ad").exists()
    rc = make_main(["--method", "wt_identity", "--board", "T3:gata4", "--wt", str(counts), "--out", str(tmp_path / "c.h5ad"),
                    "--n-cells", "all", "--log1p-counts"])
    assert rc == 0 and dense(ad.read_h5ad(tmp_path / "c.h5ad")).max() < 30
    # tiny sample with --relax-cells: written but flagged
    tiny = tmp_path / "tiny.h5ad"
    make_adata(heart_panel, 40, seed=15).write_h5ad(tiny)
    rc = make_main(["--method", "wt_identity", "--board", "T3:gata4", "--wt", str(tiny), "--out", str(tmp_path / "t.h5ad"),
                    "--relax-cells", "--n-cells", "all"])
    assert rc == 0 and "NOT uploadable" in capsys.readouterr().out
    # missing input flag is a usage error
    with pytest.raises(SystemExit):
        make_main(["--method", "pseudobulk_shift", "--board", "T1:val", "--last", str(stage), "--out", str(out), "--n-cells", "all"])
    # a non-integer --n-cells is a usage error
    with pytest.raises(SystemExit):
        make_main(["--method", "copy_last", "--board", "T2:heart:val_interp", "--last", str(stage), "--out", str(out), "--n-cells", "many"])

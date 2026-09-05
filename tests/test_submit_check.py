"""vec_submit_check on synthetic files: every rule the portal rejects on has a positive and a negative case."""
from __future__ import annotations

import json

import anndata as ad
import numpy as np
import pandas as pd
import pytest
import scipy.sparse as sp

from vec_submit_check import check, checker, known_boards, load_index, panel_for_board, panel_sha256
from vec_submit_check.guards import check_all, duplicate_rows, finite_nonneg, library_size_ratio, variance_ratio

from conftest import make_adata

BOARDS = {"T1:val", "T2:embryo:val_interp", "T2:heart:val_extrap", "T2:heart:val_interp", "T3:gata4"}


def strip(a: ad.AnnData) -> ad.AnnData:
    """A submission-shaped copy: no labels."""
    b = ad.AnnData(X=a.X.copy(), obs=pd.DataFrame(index=a.obs_names), var=pd.DataFrame(index=a.var_names))
    for k in a.obsm:
        b.obsm[k] = np.asarray(a.obsm[k]).copy()
    return b


def errors(rep):
    return "\n".join(rep["errors"])


def test_index_and_panels_are_consistent():
    assert set(known_boards()) == BOARDS
    idx = load_index()
    for key, spec in idx.items():
        genes = checker.load_panel(spec["genes_file"], spec["genes_sha256"])
        assert len(genes) == spec["n_genes"] == len(set(genes))
        assert panel_sha256(genes) == spec["genes_sha256"]
        assert spec["min_cells"] <= spec["max_cells"]
        assert spec["needs_coords"] == (spec["task"] in ("T2", "T3"))
    with pytest.raises(KeyError):
        panel_for_board("T9:nope")


def test_valid_t3_file_passes(tmp_path, heart_adata):
    f = tmp_path / "ok.h5ad"
    strip(heart_adata).write_h5ad(f)
    rep = check(f, "T3:gata4")
    assert rep["ok"], errors(rep)
    assert rep["warnings"] == []
    assert rep["info"]["n_obs"] == 1200 and rep["info"]["n_vars"] == 500
    assert rep["info"]["X_format"].startswith("dense[float32]")
    assert rep["info"]["spatial_3D_rms_radius"] > 0
    # the same file also satisfies the two heart boards (same panel, 1200 cells inside their bounds)
    assert check(f, "T2:heart:val_interp")["ok"] and check(f, "T2:heart:val_extrap")["ok"]
    # labels are tolerated with a warning
    g = tmp_path / "labels.h5ad"
    heart_adata.write_h5ad(g)
    rep = check(g, "T3:gata4")
    assert rep["ok"] and any("celltype" in w for w in rep["warnings"])


def test_gene_order_and_gene_set(tmp_path, heart_adata, heart_panel):
    a = strip(heart_adata)
    b = a[:, list(reversed(heart_panel))].copy()
    f = tmp_path / "reordered.h5ad"
    b.write_h5ad(f)
    rep = check(f, "T3:gata4")
    assert not rep["ok"] and "ORDER differs" in errors(rep)
    c = a[:, heart_panel[:498]].copy()
    g = tmp_path / "short.h5ad"
    c.write_h5ad(g)
    rep = check(g, "T3:gata4")
    assert "board expects 500" in errors(rep) and "gene names differ" in errors(rep)
    # the embryo board wants exactly its 498-gene panel: a 500-gene file is rejected, a name-mapped one passes
    rep = check(tmp_path / "ok500.h5ad" if False else f, "T2:embryo:val_interp")
    assert not rep["ok"]
    e = a[:, panel_for_board("T2:embryo:val_interp")[1]].copy()
    h = tmp_path / "embryo.h5ad"
    e.write_h5ad(h)
    assert check(h, "T2:embryo:val_interp")["ok"]


def test_cell_bounds(tmp_path, heart_panel):
    small = strip(make_adata(heart_panel, 999, seed=2))
    f = tmp_path / "small.h5ad"
    small.write_h5ad(f)
    rep = check(f, "T3:gata4")
    assert "n_obs=999 < min_cells=1000" in errors(rep)
    idx = load_index()
    assert idx["T3:gata4"]["max_cells"] == 7449
    big = strip(make_adata(heart_panel, 7450, seed=3, density=0.05))
    g = tmp_path / "big.h5ad"
    big.write_h5ad(g)
    rep = check(g, "T3:gata4")
    assert "> max_cells=7449" in errors(rep)


def test_values_and_coords(tmp_path, heart_adata):
    a = strip(heart_adata)
    neg = a.copy()
    neg.X[0, 0] = -0.5
    f = tmp_path / "neg.h5ad"
    neg.write_h5ad(f)
    assert "negative" in errors(check(f, "T3:gata4"))
    nan = a.copy()
    nan.X[1, 1] = np.nan
    g = tmp_path / "nan.h5ad"
    nan.write_h5ad(g)
    assert "NaN/inf" in errors(check(g, "T3:gata4"))
    counts = a.copy()
    counts.X = np.expm1(counts.X).astype(np.float32) * 20
    h = tmp_path / "counts.h5ad"
    counts.write_h5ad(h)
    rep = check(h, "T3:gata4")
    assert any("raw counts" in w for w in rep["warnings"])
    nocoords = a.copy()
    del nocoords.obsm["spatial_3D"]
    i = tmp_path / "nocoords.h5ad"
    nocoords.write_h5ad(i)
    assert "spatial_3D" in errors(check(i, "T3:gata4")) and "missing" in errors(check(i, "T3:gata4"))
    badc = a.copy()
    badc.obsm["spatial_3D"] = badc.obsm["spatial_3D"][:, :2]
    j = tmp_path / "coords2d.h5ad"
    badc.write_h5ad(j)
    assert "shape" in errors(check(j, "T3:gata4"))
    nanc = a.copy()
    nanc.obsm["spatial_3D"][0, 0] = np.inf
    k = tmp_path / "coordsinf.h5ad"
    nanc.write_h5ad(k)
    assert "has NaN/inf" in errors(check(k, "T3:gata4"))
    const = a.copy()
    const.X[:] = 1.0
    m = tmp_path / "const.h5ad"
    const.write_h5ad(m)
    assert "constant" in errors(check(m, "T3:gata4"))


def test_file_size_cap(tmp_path, heart_adata):
    f = tmp_path / "ok.h5ad"
    strip(heart_adata).write_h5ad(f)
    rep = check(f, "T3:gata4", max_file_mb=0.001)
    assert any("portal cap" in e for e in rep["errors"])
    assert check(f, "T3:gata4")["ok"]


def test_t1_sparse_file(tmp_path):
    spec, panel = panel_for_board("T1:val")
    assert spec["n_genes"] == 32285 and not spec["needs_coords"]
    n = 1000
    X = sp.random(n, len(panel), density=0.004, format="csr", dtype=np.float32, random_state=0)
    X.data = np.abs(X.data) * 3
    a = ad.AnnData(X=X, obs=pd.DataFrame(index=pd.Index([f"c{i}" for i in range(n)])), var=pd.DataFrame(index=pd.Index(panel)))
    f = tmp_path / "t1.h5ad"
    a.write_h5ad(f)
    rep = check(f, "T1:val")
    assert rep["ok"], errors(rep)
    assert rep["info"]["X_format"] == "csr_matrix"
    # coordinates on a board that does not need them: harmless warning
    a.obsm["spatial_3D"] = np.zeros((n, 3), dtype=np.float32)
    g = tmp_path / "t1c.h5ad"
    a.write_h5ad(g)
    rep = check(g, "T1:val")
    assert rep["ok"] and any("does not need coordinates" in w for w in rep["warnings"])
    # negative values are only a warning on T1 (log1p data should still be >= 0)
    X2 = X.copy()
    X2.data[0] = -1.0
    b = ad.AnnData(X=X2, obs=a.obs.copy(), var=a.var.copy())
    h = tmp_path / "t1neg.h5ad"
    b.write_h5ad(h)
    rep = check(h, "T1:val")
    assert rep["ok"] and any("negative" in w for w in rep["warnings"])


def test_cli_exit_codes(tmp_path, heart_adata, capsys):
    f = tmp_path / "ok.h5ad"
    strip(heart_adata).write_h5ad(f)
    out_json = tmp_path / "rep.json"
    assert checker.main(["--board", "T3:gata4", str(f), "--json", str(out_json)]) == 0
    assert json.loads(out_json.read_text(encoding="utf-8"))["ok"] is True
    assert "[PASS]" in capsys.readouterr().out
    assert checker.main(["--board", "T1:val", str(f)]) == 1
    assert "[FAIL]" in capsys.readouterr().out
    assert checker.main(["--board", "T9:nope", str(f)]) == 2
    assert checker.main(["--board", "T3:gata4", str(tmp_path / "missing.h5ad")]) == 2


def test_guards(heart_adata):
    X = heart_adata.X
    C = heart_adata.obsm["spatial_3D"]
    fn = finite_nonneg(X, C)
    assert fn["ok"] and fn["n_negative"] == 0 and fn["coords_shape_ok"]
    dup = duplicate_rows(np.vstack([X, X[:3]]), np.vstack([C, C[:3]]))
    assert dup["n_duplicate_expression_rows"] == 3 and dup["n_duplicate_coordinate_rows"] == 3
    assert library_size_ratio(X, X) == pytest.approx(1.0)
    assert variance_ratio(X, X) == pytest.approx(1.0)
    rep = check_all(X, C, X, board="T3:gata4")
    assert rep["ok"] and rep["warnings"] == [] and rep["cell_count"]["ok"]
    bad = check_all(X[:5], C[:5], X, board="T3:gata4")
    assert not bad["ok"] and any("n_cells 5 outside" in h for h in bad["hard_failures"])
    scaled = check_all(X + np.float32(np.log(10)) * (X > 0), C, X)
    assert any("library_size_ratio" in w for w in scaled["warnings"])

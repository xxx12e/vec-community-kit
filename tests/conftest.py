"""Shared fixtures: synthetic AnnData built on the real (public) board panels. No challenge data is needed."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vec_submit_check import panel_for_board  # noqa: E402

KIT_PANELS = ROOT / "data" / "panels"


def make_adata(genes, n_cells, seed=0, coords=True, celltypes=("A", "B", "C"), density=0.35, scale=1.0):
    """Synthetic log-scale-looking expression (non-negative, sparse-ish, max well below 30) with labels/coords."""
    rng = np.random.default_rng(seed)
    genes = list(genes)
    G = len(genes)
    X = rng.gamma(0.5, 1.0, size=(n_cells, G)) * scale
    X[rng.random((n_cells, G)) >= density] = 0.0
    ct = rng.choice(list(celltypes), size=n_cells)
    for i, t in enumerate(celltypes):
        j = (i * 7) % max(G - 5, 1)
        X[ct == t, j:j + 5] += 1.0                      # type-specific genes so a classifier can learn the types
    obs = pd.DataFrame({"celltype": pd.Categorical(ct)}, index=pd.Index([f"c{i}" for i in range(n_cells)]))
    a = ad.AnnData(X=X.astype(np.float32), obs=obs, var=pd.DataFrame(index=pd.Index(genes)))
    if coords:
        a.obsm["spatial_3D"] = (rng.normal(size=(n_cells, 3)) * 50.0).astype(np.float32)
    return a


@pytest.fixture(scope="session")
def heart_panel():
    """The 500-gene MERFISH panel (shared by the T2 heart boards and T3)."""
    return panel_for_board("T3:gata4")[1]


@pytest.fixture(scope="session")
def embryo_panel():
    return panel_for_board("T2:embryo:val_interp")[1]


@pytest.fixture
def heart_adata(heart_panel):
    return make_adata(heart_panel, 1200, seed=1)


@pytest.fixture(scope="session")
def tiny_data_root(tmp_path_factory, heart_panel):
    """A data root with panels/ (copied from the kit) and raw/tiny_wt.h5ad (1000 cells, valid for T3:gata4)."""
    root = tmp_path_factory.mktemp("data")
    shutil.copytree(KIT_PANELS, root / "panels")
    (root / "raw").mkdir()
    make_adata(heart_panel, 1000, seed=7).write_h5ad(root / "raw" / "tiny_wt.h5ad")
    return root

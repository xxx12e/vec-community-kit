"""vec_baselines - official-style reference rows (copy_last, wt_identity, pseudobulk_shift) and the safe
submission writer for the Virtual Embryo Challenge.

    from vec_baselines import io as bio, methods as bm
    spec, panel = bio.panel_for_board("T3:gata4")
    wt = bio.load_stage("WT_E8.75.h5ad", panel)
    X, C, info = bm.wt_identity(wt)
    bio.write_submission(X, C, panel, "pred.h5ad", "T3:gata4", n_cells="all")   # validated on write

CLI: python -m vec_baselines.make_baseline --method copy_last --board T1:val --last E9.5_RNA.h5ad --out pred.h5ad --n-cells all
"""
from . import io, methods  # noqa: F401

__version__ = "0.1.0"

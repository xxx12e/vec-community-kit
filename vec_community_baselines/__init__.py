"""vec_community_baselines - baseline generators (copy_last, wt_identity, pseudobulk_shift; the organisers' published
definitions) and the submission writer for the Virtual Embryo Challenge. The cell count is explicit and required:
`n_cells` is an int inside the board bounds or "all".

    from vec_community_baselines import io as bio, methods as bm
    spec, panel = bio.panel_for_board("T3:gata4")
    wt = bio.load_stage("WT_E8.75.h5ad", panel)
    X, C, info = bm.wt_identity(wt)
    bio.write_submission(X, C, panel, "pred.h5ad", "T3:gata4", n_cells="all")   # validated on write

CLI: python -m vec_community_baselines.make_baseline --method copy_last --board T1:val --last E9.5_RNA.h5ad --out pred.h5ad --n-cells 5000

Called `vec_baselines` until 2026-09-30; renamed at the organisers' request because that is the name of their
official baselines package. No alias is kept, so the two install side by side.
"""
from . import io, methods  # noqa: F401

__version__ = "0.1.0"

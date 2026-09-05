"""vec_local_score - run the organisers' veckit scorer locally on a pseudo-validation split, on the official
0-100 skill scale, with a seed summary.

veckit is not vendored: install it or set VECKIT_PATH (see veckit_loader.py and README.md).

    python -m vec_local_score --task T2 --setting heart --pred pred.h5ad --target E8.75.h5ad --reference E8.25_late.h5ad
    python -m vec_local_score.seed_summary --task T2 --pred pred.h5ad --target E8.75.h5ad --reference E8.25_late.h5ad --seeds 0 1 2
    python -m vec_local_score.make_pseudo_split --target E8.75.h5ad --reference E8.25_late.h5ad --out-dir pseudo/heart
"""
from .veckit_loader import INSTALL_HINT, load_veckit, veckit_available, veckit_dir  # noqa: F401

__version__ = "0.1.0"

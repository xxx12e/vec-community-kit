"""vec_local_score - run the organisers' veckit scorer locally on a pseudo-validation split built from RAW released
stages, on the 0-100 skill scale. The default output is the multi-seed band (mean, sd, min..max of the task score
over subsample seeds 0-4); --single-seed gives the old one-seed table. Follows the veckit scorer's protocol as of
veckit 0.1.1 (10 % subsample, split-half ceiling, floor row, skill scale); the organisers' scorer is the source of
truth and the wrapper may lag it.

veckit is not vendored: install it or set VECKIT_PATH (see veckit_loader.py and README.md).

    python -m vec_local_score --task T2 --setting heart --pred pred.h5ad --target E8.75.h5ad --reference E8.25_late.h5ad
    python -m vec_local_score --task T2 --setting heart --pred pred.h5ad --target E8.75.h5ad --reference E8.25_late.h5ad --single-seed
    python -m vec_local_score --task T2 --setting heart --pred a.h5ad --pred b.h5ad --target E8.75.h5ad --reference E8.25_late.h5ad
        (paired comparison: B - A per seed over the same seeds and the same draw per seed)
    python -m vec_local_score.make_pseudo_split --target E8.75.h5ad --reference E8.25_late.h5ad --out-dir pseudo/heart
        (exports one fixed split for inspection / the veckit CLI; its outputs are not inputs to vec_local_score)
"""
from .veckit_loader import (INSTALL_HINT, TESTED_VECKIT_COMMIT, TESTED_VECKIT_VERSION, load_veckit,  # noqa: F401
                            veckit_available, veckit_dir, veckit_info)

__version__ = "2026.10.0"

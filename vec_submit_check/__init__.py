"""vec_submit_check - local pre-upload checks of a Virtual Embryo Challenge prediction file against the published
board contracts (gene panel and order, cell bounds, finite non-negative float32-castable expression, coordinates,
size cap). Every rule is labelled portal / stricter / advisory in checker.py; PASS means the local format checks
passed and nothing more (not normalisation, provenance or eligibility).

    python -m vec_submit_check --board T2:heart:val_interp pred.h5ad

    from vec_submit_check import check, panel_for_board
    report = check("pred.h5ad", "T3:gata4")      # report["ok"], report["errors"], report["warnings"], report["info"]
    spec, genes = panel_for_board("T1:val")      # board bounds + ordered gene panel
"""
from .checker import (COUNTS_MAX_WARN, MAX_FILE_MB, PAGE_MIN_CELLS, check, format_report, known_boards, load_index,
                      load_panel, panel_for_board, panel_sha256, panels_dir, sha256_file)

__version__ = "0.1.0"
__all__ = ["check", "format_report", "known_boards", "load_index", "load_panel", "panel_for_board", "panel_sha256",
           "panels_dir", "sha256_file", "MAX_FILE_MB", "COUNTS_MAX_WARN", "PAGE_MIN_CELLS", "__version__"]

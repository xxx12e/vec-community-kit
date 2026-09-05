"""vec_submit_check - board-contract validator for Virtual Embryo Challenge prediction files.

    python -m vec_submit_check --board T2:heart:val_interp pred.h5ad

    from vec_submit_check import check, panel_for_board
    report = check("pred.h5ad", "T3:gata4")      # report["ok"], report["errors"], report["warnings"], report["info"]
    spec, genes = panel_for_board("T1:val")      # board bounds + ordered gene panel
"""
from .checker import (COUNTS_MAX_WARN, MAX_FILE_MB, check, format_report, known_boards, load_index, load_panel,
                      panel_for_board, panel_sha256, panels_dir, sha256_file)

__version__ = "0.1.0"
__all__ = ["check", "format_report", "known_boards", "load_index", "load_panel", "panel_for_board", "panel_sha256",
           "panels_dir", "sha256_file", "MAX_FILE_MB", "COUNTS_MAX_WARN", "__version__"]

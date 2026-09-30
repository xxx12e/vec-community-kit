"""pyproject.toml: metadata agrees with requirements.txt and the packages, the console commands resolve, and a built
wheel carries the board contracts (vec_submit_check/panels/) so an installed copy works outside the repository."""
from __future__ import annotations

import importlib
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
tomllib = pytest.importorskip("tomllib")          # Python 3.11+; the kit itself runs on 3.10


def pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def requirement_lines() -> list:
    return [x.strip() for x in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if x.strip() and not x.strip().startswith("#")]


def test_requirements_txt_matches_pyproject():
    proj = pyproject()["project"]
    reqs = requirement_lines()
    assert reqs == proj["dependencies"] + proj["optional-dependencies"]["test"], reqs
    assert "veckit" in proj["optional-dependencies"]["score"][0]
    assert "46d41e63f42a9aab815db20b742feeccd249cb17" in proj["optional-dependencies"]["score"][0]


def test_versions_and_packages_agree():
    proj = pyproject()
    version = proj["project"]["version"]
    packages = proj["tool"]["setuptools"]["packages"]
    top = sorted({p.split(".")[0] for p in packages})
    assert top == ["vec_agent_evidence", "vec_community_baselines", "vec_local_score", "vec_submit_check"]
    assert "vec_baselines" not in " ".join(packages)
    for name in top:
        assert importlib.import_module(name).__version__ == version, name
    assert proj["tool"]["setuptools"]["package-dir"] == {"vec_submit_check.panels": "data/panels"}


def test_console_scripts_resolve():
    scripts = pyproject()["project"]["scripts"]
    assert set(scripts) == {"vec-community-check", "vec-community-baseline", "vec-community-score",
                            "vec-community-split", "vec-community-evidence"}
    for target in scripts.values():
        mod, func = target.split(":")
        assert callable(getattr(importlib.import_module(mod), func)), target


def test_panel_files_are_package_data():
    patterns = pyproject()["tool"]["setuptools"]["package-data"]["vec_submit_check.panels"]
    files = sorted(p.name for p in (ROOT / "data" / "panels").iterdir() if p.is_file())
    for name in files:
        assert any(Path(name).match(pat) for pat in patterns), name


def _setuptools_ok() -> bool:
    try:
        import setuptools
        major = int(re.match(r"\d+", setuptools.__version__).group())
        return major >= 77
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _setuptools_ok(), reason="building the wheel offline needs setuptools>=77 in this environment")
def test_wheel_installs_and_finds_its_panels(tmp_path):
    """Build the wheel offline (no build isolation, no dependencies), install it into a scratch directory and use it
    from a directory that has no data/panels: the validator must find the copy installed with the package."""
    src = tmp_path / "src"                           # build from a copy: setuptools writes build/ and *.egg-info
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for d in ("vec_submit_check", "vec_community_baselines", "vec_local_score", "vec_agent_evidence", "data/panels"):
        shutil.copytree(ROOT / d, src / d, ignore=ignore)
    for f in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copy2(ROOT / f, src / f)
    wheels = tmp_path / "wheels"
    r = subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "-q", "-w",
                        str(wheels), str(src)], capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout + r.stderr
    whl = sorted(wheels.glob("vec_community_kit-*.whl"))
    assert len(whl) == 1, list(wheels.iterdir())
    names = zipfile.ZipFile(whl[0]).namelist()
    for n in ("vec_submit_check/panels/index.json", "vec_submit_check/panels/T1__val.genes.txt",
              "vec_submit_check/panels/T3__gata4.genes.txt", "vec_community_baselines/make_baseline.py",
              "vec_local_score/local_score.py", "vec_agent_evidence/hooks/guard.py",
              "vec_agent_evidence/example_prompt.md", "vec_agent_evidence/example_settings.json",
              "vec_agent_evidence/example_opencode.json", "vec_agent_evidence/opencode.py"):
        assert n in names, n
    assert not any(n.startswith(("vec_baselines/", "tests/", "data/", "scratchpad/")) for n in names)
    entry_points = [n for n in names if n.endswith(".dist-info/entry_points.txt")]
    ep = zipfile.ZipFile(whl[0]).read(entry_points[0]).decode("utf-8")
    assert "vec-community-check = vec_submit_check.checker:main" in ep

    site = tmp_path / "site"
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "--no-index", "-q", "--target", str(site),
                        str(whl[0])], capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout + r.stderr
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ("VEC_PANELS_DIR", "PYTHONPATH")}
    env["PYTHONPATH"] = str(site)
    code = ("import vec_submit_check as v, vec_community_baselines as b, vec_agent_evidence.common as c; "
            "print(v.panels_dir()); print(len(v.known_boards())); print(v.panel_for_board('T3:gata4')[0]['n_genes']); "
            "print(b.__file__); print(c.DEFAULT_RUNS_ROOT)")
    r = subprocess.run([sys.executable, "-c", code], cwd=str(elsewhere), env=env, capture_output=True, text=True,
                       timeout=300)
    assert r.returncode == 0, r.stderr
    panels, n_boards, n_genes, bfile, runs_root = r.stdout.strip().splitlines()
    assert Path(panels).resolve() == (site / "vec_submit_check" / "panels").resolve()
    assert n_boards == "5" and n_genes == "500"
    assert Path(bfile).resolve().is_relative_to(site.resolve())
    assert Path(runs_root).resolve() == (elsewhere / "runs").resolve()   # never into site-packages

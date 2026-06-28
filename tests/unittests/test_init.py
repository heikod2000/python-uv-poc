from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app import (
    _find_project_root,
    _get_dev_dependency_names,
    _get_direct_dependency_names,
    _update_pyproject_dependencies_block,
    _update_pyproject_dev_block,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _write_pyproject(path: Path, deps: list[str], dev_deps: list[str] | None = None) -> Path:
    content = "[project]\n"
    if deps:
        lines = "\n".join(f'    "{d}",' for d in deps)
        content += f"dependencies = [\n{lines}\n]\n"
    else:
        content += "dependencies = []\n"
    if dev_deps is not None:
        content += "\n[dependency-groups]\n"
        if dev_deps:
            lines = "\n".join(f'    "{d}",' for d in dev_deps)
            content += f"dev = [\n{lines}\n]\n"
        else:
            content += "dev = []\n"
    pyproject = path / "pyproject.toml"
    pyproject.write_text(content, encoding="utf-8")
    return pyproject


# ---------------------------------------------------------------------------
# _find_project_root
# ---------------------------------------------------------------------------


def test_find_project_root_in_cwd(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").touch()
    with patch("app.Path.cwd", return_value=tmp_path):
        assert _find_project_root() == tmp_path


def test_find_project_root_in_parent(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").touch()
    child = tmp_path / "sub" / "dir"
    child.mkdir(parents=True)
    with patch("app.Path.cwd", return_value=child):
        assert _find_project_root() == tmp_path


def test_find_project_root_not_found(tmp_path: Path) -> None:
    with patch("app.Path.cwd", return_value=tmp_path), pytest.raises(SystemExit):
        _find_project_root()


# ---------------------------------------------------------------------------
# _get_direct_dependency_names
# ---------------------------------------------------------------------------


def test_get_deps_simple_pin(tmp_path: Path) -> None:
    pyproject = _write_pyproject(tmp_path, ["fastapi==0.120.2"])
    assert _get_direct_dependency_names(pyproject) == {"fastapi"}


def test_get_deps_ge_specifier(tmp_path: Path) -> None:
    pyproject = _write_pyproject(tmp_path, ["uvicorn>=0.30"])
    assert _get_direct_dependency_names(pyproject) == {"uvicorn"}


def test_get_deps_strips_extras(tmp_path: Path) -> None:
    pyproject = _write_pyproject(tmp_path, ["uvicorn[standard]>=0.30"])
    assert _get_direct_dependency_names(pyproject) == {"uvicorn"}


def test_get_deps_multiple(tmp_path: Path) -> None:
    pyproject = _write_pyproject(tmp_path, ["fastapi==0.120.2", "uvicorn>=0.30", "httpx"])
    assert _get_direct_dependency_names(pyproject) == {"fastapi", "uvicorn", "httpx"}


def test_get_deps_empty(tmp_path: Path) -> None:
    pyproject = _write_pyproject(tmp_path, [])
    assert _get_direct_dependency_names(pyproject) == set()


def test_get_deps_no_project_section(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[tool.ruff]\nline-length = 100\n", encoding="utf-8")
    assert _get_direct_dependency_names(pyproject) == set()


# ---------------------------------------------------------------------------
# _get_dev_dependency_names
# ---------------------------------------------------------------------------


def test_get_dev_deps_simple(tmp_path: Path) -> None:
    pyproject = _write_pyproject(tmp_path, [], dev_deps=["pytest>=8.0"])
    assert _get_dev_dependency_names(pyproject) == {"pytest"}


def test_get_dev_deps_multiple(tmp_path: Path) -> None:
    pyproject = _write_pyproject(tmp_path, [], dev_deps=["pytest>=8.0", "ruff>=0.5.0", "httpx==0.27.0"])
    assert _get_dev_dependency_names(pyproject) == {"pytest", "ruff", "httpx"}


def test_get_dev_deps_empty(tmp_path: Path) -> None:
    pyproject = _write_pyproject(tmp_path, [], dev_deps=[])
    assert _get_dev_dependency_names(pyproject) == set()


def test_get_dev_deps_no_section(tmp_path: Path) -> None:
    pyproject = _write_pyproject(tmp_path, ["fastapi==0.120.2"])
    assert _get_dev_dependency_names(pyproject) == set()


# ---------------------------------------------------------------------------
# _update_pyproject_dependencies_block
# ---------------------------------------------------------------------------


def test_update_replaces_pinned_version(tmp_path: Path) -> None:
    pyproject = _write_pyproject(tmp_path, ["fastapi==0.120.2"])
    _update_pyproject_dependencies_block(pyproject, {"fastapi": "0.136.0"})
    assert "fastapi==0.136.0" in pyproject.read_text(encoding="utf-8")


def test_update_leaves_unmatched_deps_unchanged(tmp_path: Path) -> None:
    pyproject = _write_pyproject(tmp_path, ["fastapi==0.120.2", "uvicorn>=0.30"])
    _update_pyproject_dependencies_block(pyproject, {"fastapi": "0.136.0"})
    text = pyproject.read_text(encoding="utf-8")
    assert "fastapi==0.136.0" in text
    assert "uvicorn>=0.30" in text


def test_update_multiple_packages(tmp_path: Path) -> None:
    pyproject = _write_pyproject(tmp_path, ["fastapi==0.120.2", "uvicorn>=0.30"])
    _update_pyproject_dependencies_block(pyproject, {"fastapi": "0.136.0", "uvicorn": "0.34.0"})
    text = pyproject.read_text(encoding="utf-8")
    assert "fastapi==0.136.0" in text
    assert "uvicorn==0.34.0" in text


def test_update_no_dependencies_block_raises(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[project]\nname = 'x'\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        _update_pyproject_dependencies_block(pyproject, {"fastapi": "0.136.0"})


# ---------------------------------------------------------------------------
# _update_pyproject_dev_block
# ---------------------------------------------------------------------------


def test_update_dev_replaces_version(tmp_path: Path) -> None:
    pyproject = _write_pyproject(tmp_path, [], dev_deps=["pytest>=8.0"])
    _update_pyproject_dev_block(pyproject, {"pytest": "9.0.0"})
    assert "pytest==9.0.0" in pyproject.read_text(encoding="utf-8")


def test_update_dev_leaves_unmatched_unchanged(tmp_path: Path) -> None:
    pyproject = _write_pyproject(tmp_path, [], dev_deps=["pytest>=8.0", "ruff>=0.5.0"])
    _update_pyproject_dev_block(pyproject, {"pytest": "9.0.0"})
    text = pyproject.read_text(encoding="utf-8")
    assert "pytest==9.0.0" in text
    assert "ruff>=0.5.0" in text


def test_update_dev_no_block_raises(tmp_path: Path) -> None:
    pyproject = _write_pyproject(tmp_path, ["fastapi==0.120.2"])
    with pytest.raises(SystemExit):
        _update_pyproject_dev_block(pyproject, {"pytest": "9.0.0"})


def test_update_dev_does_not_touch_regular_deps(tmp_path: Path) -> None:
    pyproject = _write_pyproject(tmp_path, ["fastapi==0.120.2"], dev_deps=["pytest>=8.0"])
    _update_pyproject_dev_block(pyproject, {"pytest": "9.0.0"})
    text = pyproject.read_text(encoding="utf-8")
    assert "fastapi==0.120.2" in text
    assert "pytest==9.0.0" in text


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def test_main_no_outdated(tmp_path: Path) -> None:
    from app import main

    _write_pyproject(tmp_path, ["fastapi==0.120.2"])

    outdated_json = json.dumps([])

    with (
        patch("app._find_project_root", return_value=tmp_path),
        patch("app.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(stdout=outdated_json)
        main()  # must not raise


def test_main_updates_direct_dep(tmp_path: Path) -> None:
    from app import main

    pyproject = _write_pyproject(tmp_path, ["fastapi==0.120.2"])

    outdated_json = json.dumps(
        [
            {"name": "fastapi", "version": "0.120.2", "latest_version": "0.136.0"},
        ]
    )

    with (
        patch("app._find_project_root", return_value=tmp_path),
        patch("app.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(stdout=outdated_json)
        main()

    assert "fastapi==0.136.0" in pyproject.read_text(encoding="utf-8")


def test_main_updates_dev_dep(tmp_path: Path) -> None:
    from app import main

    pyproject = _write_pyproject(tmp_path, ["fastapi==0.120.2"], dev_deps=["pytest>=8.0"])

    outdated_json = json.dumps(
        [
            {"name": "pytest", "version": "8.0.0", "latest_version": "9.0.0"},
        ]
    )

    with (
        patch("app._find_project_root", return_value=tmp_path),
        patch("app.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(stdout=outdated_json)
        main()

    text = pyproject.read_text(encoding="utf-8")
    assert "pytest==9.0.0" in text
    assert "fastapi==0.120.2" in text


def test_main_updates_both_groups(tmp_path: Path) -> None:
    from app import main

    pyproject = _write_pyproject(tmp_path, ["fastapi==0.120.2"], dev_deps=["pytest>=8.0"])

    outdated_json = json.dumps(
        [
            {"name": "fastapi", "version": "0.120.2", "latest_version": "0.136.0"},
            {"name": "pytest", "version": "8.0.0", "latest_version": "9.0.0"},
        ]
    )

    with (
        patch("app._find_project_root", return_value=tmp_path),
        patch("app.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(stdout=outdated_json)
        main()

    text = pyproject.read_text(encoding="utf-8")
    assert "fastapi==0.136.0" in text
    assert "pytest==9.0.0" in text


def test_main_ignores_transitive_dep(tmp_path: Path) -> None:
    from app import main

    pyproject = _write_pyproject(tmp_path, ["fastapi==0.120.2"])

    outdated_json = json.dumps(
        [
            {"name": "starlette", "version": "0.40.0", "latest_version": "0.41.0"},
        ]
    )

    with (
        patch("app._find_project_root", return_value=tmp_path),
        patch("app.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(stdout=outdated_json)
        main()

    text = pyproject.read_text(encoding="utf-8")
    assert "starlette" not in text
    assert "fastapi==0.120.2" in text

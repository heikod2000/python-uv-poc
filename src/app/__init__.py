from __future__ import annotations

import json
import re
import subprocess
import tomllib
from pathlib import Path


def _find_project_root() -> Path:
    """
    Starting from the current working directory, walk upwards until a
    pyproject.toml is found. This makes the script independent of its
    own file location.
    """
    path = Path.cwd().resolve()
    for candidate_dir in (path, *path.parents):
        candidate = candidate_dir / "pyproject.toml"
        if candidate.exists():
            return candidate_dir

    print("No pyproject.toml found upwards from current working directory.")
    raise SystemExit(1)


def _parse_package_names(deps: list[str]) -> set[str]:
    """Extract plain package names from a list of PEP 508 dependency strings."""
    names: set[str] = set()
    for dep in deps:
        token = dep
        if "[" in token:
            token = token.split("[", 1)[0]
        for sep in ("<", ">", "=", "!", "~", " "):
            if sep in token:
                token = token.split(sep, 1)[0]
        name = token.strip()
        if name:
            names.add(name)
    return names


def _get_direct_dependency_names(pyproject_path: Path) -> set[str]:
    """Read [project].dependencies and return package names."""
    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)
    return _parse_package_names(data.get("project", {}).get("dependencies", []))


def _get_dev_dependency_names(pyproject_path: Path) -> set[str]:
    """Read [dependency-groups].dev and return package names."""
    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)
    return _parse_package_names(data.get("dependency-groups", {}).get("dev", []))


def _apply_versions_to_dep_list(deps: list[str], new_versions: dict[str, str]) -> list[str]:
    """Return dep list with updated versions; unchanged entries are kept as-is."""
    updated: list[str] = []
    for dep in deps:
        base = dep
        if "[" in base:
            base = base.split("[", 1)[0]
        for sep in ("<", ">", "=", "!", "~", " "):
            if sep in base:
                base = base.split(sep, 1)[0]
        name = base.strip()
        updated.append(f"{name}=={new_versions[name]}" if name in new_versions else dep)
    return updated


def _update_pyproject_dependencies_block(pyproject_path: Path, new_versions: dict[str, str]) -> None:
    """
    Replace the [project].dependencies block in pyproject.toml with updated versions.
    """
    text = pyproject_path.read_text(encoding="utf-8")
    pattern = re.compile(r"dependencies\s*=\s*\[(.*?)\]", re.DOTALL)
    match = pattern.search(text)
    if not match:
        print("Kein [project].dependencies Block in pyproject.toml gefunden.")
        raise SystemExit(1)

    data = tomllib.loads(text)
    deps = data.get("project", {}).get("dependencies", [])
    updated_deps = _apply_versions_to_dep_list(deps, new_versions)

    lines = ["dependencies = ["]
    for d in updated_deps:
        lines.append(f'    "{d}",')
    lines.append("]")
    new_block = "\n".join(lines)

    start, end = match.span()
    pyproject_path.write_text(text[:start] + new_block + text[end:], encoding="utf-8")


def _update_pyproject_dev_block(pyproject_path: Path, new_versions: dict[str, str]) -> None:
    """
    Replace the [dependency-groups].dev block in pyproject.toml with updated versions.
    """
    text = pyproject_path.read_text(encoding="utf-8")
    pattern = re.compile(r"dev\s*=\s*\[(.*?)\]", re.DOTALL)
    match = pattern.search(text)
    if not match:
        print("Kein [dependency-groups].dev Block in pyproject.toml gefunden.")
        raise SystemExit(1)

    data = tomllib.loads(text)
    deps = data.get("dependency-groups", {}).get("dev", [])
    updated_deps = _apply_versions_to_dep_list(deps, new_versions)

    lines = ["dev = ["]
    for d in updated_deps:
        lines.append(f'    "{d}",')
    lines.append("]")
    new_block = "\n".join(lines)

    start, end = match.span()
    pyproject_path.write_text(text[:start] + new_block + text[end:], encoding="utf-8")


def main() -> None:
    project_root = _find_project_root()
    pyproject_path = project_root / "pyproject.toml"

    if not pyproject_path.exists():
        print(f"pyproject.toml nicht gefunden unter {pyproject_path}")
        raise SystemExit(1)

    direct_deps = _get_direct_dependency_names(pyproject_path)
    dev_deps = _get_dev_dependency_names(pyproject_path)

    if not direct_deps and not dev_deps:
        print("Keine direkten Dependencies in pyproject.toml gefunden.")
        return

    if direct_deps:
        print(f"Direkte Dependencies: {', '.join(sorted(direct_deps))}")
    if dev_deps:
        print(f"Dev Dependencies: {', '.join(sorted(dev_deps))}")

    result = subprocess.run(
        ["uv", "pip", "list", "--outdated", "--format", "json"],
        capture_output=True,
        text=True,
        check=True,
    )
    outdated = json.loads(result.stdout)

    regular_versions: dict[str, str] = {}
    dev_versions: dict[str, str] = {}

    for pkg in outdated:
        name = pkg["name"]
        current = pkg["version"]
        latest = pkg["latest_version"]
        if name in direct_deps:
            print(f"[dependencies] {name}: {current} -> {latest}")
            regular_versions[name] = latest
        elif name in dev_deps:
            print(f"[dev] {name}: {current} -> {latest}")
            dev_versions[name] = latest

    if not regular_versions and not dev_versions:
        print("Keine veralteten Dependencies gefunden.")
        return

    if regular_versions:
        _update_pyproject_dependencies_block(pyproject_path, regular_versions)
    if dev_versions:
        _update_pyproject_dev_block(pyproject_path, dev_versions)

    print("pyproject.toml aktualisiert.")
    print("Wenn du das Env anpassen willst, danach z. B.:")
    print("  uv sync")
    print("oder")
    print("  uv lock --upgrade")


if __name__ == "__main__":
    main()

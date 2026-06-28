# uv commands

```shell
# create venv
uv venv

uv tree
uv pip list --outdated
```

## updates

- `uv` regelmäßig aktualisieren

```shell
pip install --upgrade uv
```

**Update-Problem**: Via `uv pip list --outdated` können neuere Versionen von Dependencies angezeigt werden.
Interessant sind nur die direkten Dependencies in `pyproject.toml`. Nur diese müssen aktualisiert werden.
Die indirekten Dependencies werden nachgezogen. `UV` kann das derzeit nicht. Als Workaround gibt es ein 
Python-Script, dass für alle Dependencies in der `pyproject.toml` die aktuellen Versionen in der Datei setzt.
Anschließend wird `uv sync` zur Aktualisierung des `venv` aufgerufen. 

```shell
uv run update-packages
# aktualisiert die Dependencies in der pyproject.toml, anschließend muss 
uv sync
# ausgeführt werden.
```

- vereinfacht mit `task update`

## Projektstart

Usecase: Code aus git auschecken und Entwicklungsumgebung einrichten

- Python installalieren (Depot)
- *uv* mit `pip install uv` installieren
- Soucecodeprojekt klonen und mit IDE öffnen

---

## Projekt aufsetzen (uv + FastAPI + pytest)

### Voraussetzungen

```bash
# uv installieren (falls nicht vorhanden)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 1. Projekt anlegen

```bash
uv init my-project
cd my-project
```

### 2. Source-Layout einrichten

```bash
mkdir -p src/app tests/unittests
touch src/app/__init__.py src/app/server.py
touch tests/__init__.py tests/unittests/__init__.py
```

### 3. Dependencies hinzufügen

```bash
# Laufzeit-Dependencies
uv add fastapi uvicorn python-multipart

# Dev-Dependencies
uv add --group dev pytest pytest-cov ruff httpx
```

### 4. `pyproject.toml` anpassen

Folgende Abschnitte ergänzen:

```toml
[build-system]
requires = ["uv_build>=0.7,<0.8"]
build-backend = "uv_build"

[tool.uv]
package = true
link-mode = "copy"          # verhindert Symlink-Probleme auf Windows

[tool.uv.build-backend]
module-name = "app"         # Modul liegt unter src/app/

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests/unittests"]
addopts = "--cov=app --cov-report=term-missing"

[tool.coverage.run]
source = ["app"]

[tool.ruff]
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "UP", "B", "SIM", "I"]
preview = true
```

### 5. Sync & Verify

```bash
uv sync                                        # .venv anlegen und alle Deps installieren
uv run pytest                                  # Tests
uv run ruff check .                            # Linter
uv run uvicorn app.server:app --reload         # Dev-Server
```

### Danach bei jeder Änderung an `pyproject.toml`

```bash
uv sync        # Lock-File + .venv aktuell halten
```

> **Hinweis zu `link-mode = "copy"`:** Ohne diese Option legt `uv` unter Windows Symlinks an,
> was je nach Dateisystem / NTFS-Berechtigungen fehlschlägt. Mit `copy` wird immer eine echte Kopie angelegt.
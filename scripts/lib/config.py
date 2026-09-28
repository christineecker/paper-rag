"""Home resolution and config.json handling for paper-rag.

Home resolution order (highest wins):
1. --home <path> / --home-name <name> CLI flag (passed in explicitly by caller)
2. PAPER_RAG_HOME env var
3. ./.paper-rag-home in cwd (project override: raw path, or "name:<name>")
4. "current" key in ~/.config/paper-rag/homes.json
5. default ~/.local/share/paper-rag
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

HOMES_REGISTRY = Path.home() / ".config" / "paper-rag" / "homes.json"
PROJECT_OVERRIDE_FILE = ".paper-rag-home"
DEFAULT_HOME = Path.home() / ".local" / "share" / "paper-rag"

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"

DEFAULT_CONFIG = {
    "embedding_model": DEFAULT_EMBEDDING_MODEL,
}


def read_homes_registry() -> dict:
    if not HOMES_REGISTRY.exists():
        return {"homes": {}, "current": None}
    try:
        return json.loads(HOMES_REGISTRY.read_text())
    except (json.JSONDecodeError, OSError):
        return {"homes": {}, "current": None}


def write_homes_registry(data: dict) -> None:
    HOMES_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    HOMES_REGISTRY.write_text(json.dumps(data, indent=2) + "\n")


def _read_project_override() -> Optional[str]:
    override_path = Path.cwd() / PROJECT_OVERRIDE_FILE
    if not override_path.exists():
        return None
    line = override_path.read_text().strip().splitlines()
    if not line:
        return None
    value = line[0].strip()
    if not value:
        return None
    if value.startswith("name:"):
        name = value[len("name:"):].strip()
        registry = read_homes_registry()
        homes = registry.get("homes", {})
        if name in homes:
            return homes[name]
        return None
    return value


def resolve_home(home: Optional[str] = None, home_name: Optional[str] = None) -> Path:
    """Resolve the active paper-rag home directory, highest-priority source wins."""
    if home:
        return Path(home).expanduser().resolve()
    if home_name:
        registry = read_homes_registry()
        homes = registry.get("homes", {})
        if home_name not in homes:
            raise ValueError(
                f"Unknown home name '{home_name}'. Known homes: {list(homes.keys())}"
            )
        return Path(homes[home_name]).expanduser().resolve()

    env_home = os.environ.get("PAPER_RAG_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()

    project_override = _read_project_override()
    if project_override:
        return Path(project_override).expanduser().resolve()

    registry = read_homes_registry()
    current = registry.get("current")
    homes = registry.get("homes", {})
    if current and current in homes:
        return Path(homes[current]).expanduser().resolve()

    return DEFAULT_HOME.resolve()


def chroma_dir(home: Path) -> Path:
    return home / "chroma"


def papers_dir(home: Path) -> Path:
    return home / "papers"


def bm25_dir(home: Path) -> Path:
    return home / "bm25"


def config_path(home: Path) -> Path:
    return home / "config.json"


def load_config(home: Path) -> dict:
    path = config_path(home)
    if not path.exists():
        return dict(DEFAULT_CONFIG)
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        data = {}
    merged = dict(DEFAULT_CONFIG)
    merged.update(data)
    return merged


def write_config(home: Path, config: dict) -> None:
    config_path(home).write_text(json.dumps(config, indent=2) + "\n")


def resolve_embedding_model(home: Path, cli_value: Optional[str] = None) -> str:
    """--embedding-model flag > PAPER_RAG_EMBEDDING_MODEL env > config.json > default."""
    if cli_value:
        return cli_value
    env_value = os.environ.get("PAPER_RAG_EMBEDDING_MODEL")
    if env_value:
        return env_value
    config = load_config(home)
    return config.get("embedding_model", DEFAULT_EMBEDDING_MODEL)


def model_slug(embedding_model: str) -> str:
    return embedding_model.replace("/", "_")


def collection_name(embedding_model: str) -> str:
    return f"papers__{model_slug(embedding_model)}"

"""paper-rag home initialization / registry management.

Handles three call shapes (dispatched from commands/*.md):
  python init.py <path> [--name NAME] [--use]        # /paper-rag:init
  python init.py --use-only <name>                    # /paper-rag:use
  python init.py --whoami "<name>"                     # /paper-rag:whoami
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import config as cfg  # noqa: E402

app = typer.Typer(add_completion=False)


def _init_home(path: str, name: Optional[str], use: Optional[bool]) -> None:
    resolved = Path(path).expanduser().resolve()
    fresh = not resolved.exists()

    (resolved / "chroma").mkdir(parents=True, exist_ok=True)
    (resolved / "papers").mkdir(parents=True, exist_ok=True)

    config_file = cfg.config_path(resolved)
    if not config_file.exists():
        cfg.write_config(resolved, dict(cfg.DEFAULT_CONFIG))

    registry = cfg.read_homes_registry()
    homes = registry.setdefault("homes", {})
    home_name = name or resolved.name
    is_first_home = len(homes) == 0
    homes[home_name] = str(resolved)

    became_current = use if use is not None else is_first_home
    if became_current:
        registry["current"] = home_name

    cfg.write_homes_registry(registry)

    result = {
        "path": str(resolved),
        "name": home_name,
        "fresh": fresh,
        "current": registry.get("current") == home_name,
    }
    print(json.dumps(result, indent=2))


def _use_home(name: str) -> None:
    registry = cfg.read_homes_registry()
    homes = registry.get("homes", {})
    if name not in homes:
        print(
            f"error: unknown home '{name}'. Known homes: {list(homes.keys())}",
            file=sys.stderr,
        )
        raise typer.Exit(code=1)
    registry["current"] = name
    cfg.write_homes_registry(registry)
    print(json.dumps({"current": name, "path": homes[name]}, indent=2))


def _set_whoami(author_name: str) -> None:
    home = cfg.resolve_home()
    home.mkdir(parents=True, exist_ok=True)
    config = cfg.load_config(home)
    config["author_name"] = author_name
    cfg.write_config(home, config)
    print(json.dumps({"home": str(home), "author_name": author_name}, indent=2))


@app.command()
def main(
    path: Optional[str] = typer.Argument(None),
    name: Optional[str] = typer.Option(None, "--name"),
    use: Optional[bool] = typer.Option(None, "--use/--no-use"),
    use_only: Optional[str] = typer.Option(None, "--use-only"),
    whoami: Optional[str] = typer.Option(None, "--whoami"),
):
    if whoami is not None:
        _set_whoami(whoami)
        return
    if use_only is not None:
        _use_home(use_only)
        return
    if path is None:
        print("error: <path> is required", file=sys.stderr)
        raise typer.Exit(code=1)
    _init_home(path, name, use)


if __name__ == "__main__":
    app()

"""Local working directories shared by the CLI, Skill and MCP."""

import json
import os
import tempfile
from pathlib import Path

CONFIG = Path.home() / ".config/phocus-cli/paths.json"
PICTURES = Path.home() / "Pictures"
DEFAULTS = {
    "library": PICTURES,
    "watch": PICTURES / "Phocus CLI" / "待处理",
    "spool": PICTURES / "Phocus CLI" / "Phocus 输出",
    "out": PICTURES / "Phocus CLI" / "成片",
}


def read_paths():
    if not CONFIG.exists():
        return DEFAULTS.copy()
    data = json.loads(CONFIG.read_text())
    return {key: Path(data[key]).expanduser().resolve() for key in DEFAULTS}


def save_paths(paths):
    if (
        paths["watch"] == paths["out"]
        or paths["watch"] in paths["out"].parents
        or paths["watch"] == paths["spool"]
        or paths["watch"] in paths["spool"].parents
    ):
        raise ValueError("成片和 Phocus 输出目录必须位于待处理目录之外")
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=CONFIG.parent, delete=False) as f:
        json.dump(
            {k: str(p) for k, p in paths.items()}, f, ensure_ascii=False, indent=2
        )
        name = f.name
    os.replace(name, CONFIG)

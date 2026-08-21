from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

REGISTRY_PATH = Path("config/data_sources.json")

@dataclass(frozen=True)
class DatasetSpec:
    id: str
    name: str
    mode: str
    formats: tuple[str, ...]
    domain: str
    required: tuple[str, ...]
    aliases: dict[str, tuple[str, ...]]
    api_url_env: str | None = None
    api_key_env: str | None = None
    source_url_env: str | None = None

def load_registry(path: Path = REGISTRY_PATH) -> dict[str, DatasetSpec]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        item["id"]: DatasetSpec(
            id=item["id"], name=item["name"], mode=item["mode"],
            formats=tuple(item["formats"]), domain=item["domain"],
            required=tuple(item.get("required", [])),
            aliases={key: tuple(value) for key, value in item.get("aliases", {}).items()},
            api_url_env=item.get("api_url_env"), api_key_env=item.get("api_key_env"),
            source_url_env=item.get("source_url_env"),
        ) for item in payload["datasets"]
    }

def get_dataset(dataset_id: str) -> DatasetSpec:
    registry = load_registry()
    if dataset_id not in registry:
        raise KeyError(f"등록되지 않은 dataset_id: {dataset_id}")
    return registry[dataset_id]

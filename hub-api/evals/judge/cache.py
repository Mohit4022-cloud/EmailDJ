from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class JudgeCache:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def build_key(
        self,
        *,
        case_id: str,
        model_version: str,
        prompt_contract_hash: str,
        candidate_id: str = "default",
        eval_mode: str = "full",
        rubric_version: str = "enterprise_outbound_v1",
        extra: str = "",
    ) -> str:
        raw = "|".join(
            [
                case_id.strip(),
                model_version.strip(),
                prompt_contract_hash.strip(),
                candidate_id.strip(),
                eval_mode.strip(),
                rubric_version.strip(),
                extra.strip(),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> dict[str, Any] | None:
        path = self._path_for(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def put(self, key: str, payload: dict[str, Any]) -> None:
        path = self._path_for(key)
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    def _path_for(self, key: str) -> Path:
        shard = key[:2]
        directory = self.root_dir / shard
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{key}.json"


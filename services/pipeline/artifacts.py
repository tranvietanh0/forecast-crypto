from __future__ import annotations

from pathlib import Path
import json
import uuid



def write_json_artifact(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            current_payload = json.loads(path.read_text(encoding="utf-8"))
            if current_payload == payload:
                return
        except json.JSONDecodeError:
            pass

    temp_path = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    temp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temp_path.replace(path)

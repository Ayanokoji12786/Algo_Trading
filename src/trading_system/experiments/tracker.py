"""Append-only experiment log (Prompt.md S26, S29): every run is recorded,
including failures, so the multiple-testing problem stays visible instead of
hidden by only keeping the runs that looked good.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExperimentRecord:
    experiment_id: str
    hypothesis: str
    config: dict[str, Any]
    data_description: str
    result: dict[str, Any]
    conclusion: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ExperimentTracker:
    def __init__(self, log_path: str | Path):
        self._log_path = Path(log_path)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, record: ExperimentRecord) -> None:
        with self._log_path.open("a") as f:
            f.write(json.dumps(asdict(record), default=str) + "\n")

    def all_records(self) -> list[dict[str, Any]]:
        if not self._log_path.exists():
            return []
        with self._log_path.open() as f:
            return [json.loads(line) for line in f if line.strip()]

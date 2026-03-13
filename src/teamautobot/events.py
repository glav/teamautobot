from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class Event:
    id: str
    type: str
    source: str
    target: str | None
    correlation_id: str | None
    timestamp: str
    payload: dict[str, Any] = field(default_factory=dict)


class JsonlEventStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: Event) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), sort_keys=True) + "\n")


class EventBus:
    def __init__(self, store: JsonlEventStore) -> None:
        self._store = store
        self._events: list[Event] = []

    @property
    def events(self) -> tuple[Event, ...]:
        return tuple(self._events)

    @property
    def path(self) -> Path:
        return self._store.path

    def emit(
        self,
        event_type: str,
        *,
        source: str,
        payload: dict[str, Any],
        target: str | None = None,
        correlation_id: str | None = None,
    ) -> Event:
        event = Event(
            id=str(uuid4()),
            type=event_type,
            source=source,
            target=target,
            correlation_id=correlation_id,
            timestamp=datetime.now(UTC).isoformat(),
            payload=payload,
        )
        self._events.append(event)
        self._store.append(event)
        return event

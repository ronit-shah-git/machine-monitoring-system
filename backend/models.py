from dataclasses import dataclass, asdict


@dataclass
class DowntimeEntry:
    start: int
    end: int = 0
    is_active: bool = True
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DowntimeEntry":
        return cls(
            start=int(data.get("start", 0)),
            end=int(data.get("end", 0)),
            is_active=bool(data.get("is_active", True)),
            reason=str(data.get("reason", "")),
        )
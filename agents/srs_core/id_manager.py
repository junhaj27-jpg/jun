import re, logging
from dataclasses import dataclass, field

logger  = logging.getLogger(__name__)
_PATTERN = re.compile(r"^([A-Z][A-Z0-9_]*)-(\d+)$")

@dataclass
class IDRegistry:
    _used: dict[str, set[int]] = field(default_factory=dict)

    @classmethod
    def from_existing(cls, existing: list[dict]):
        reg = cls()
        for r in existing:
            p, n = _parse(_norm_id(r.get("requirement_id", "")))
            if p: reg._used.setdefault(p, set()).add(n)
        return reg

    def next_id(self, prefix: str) -> str:
        p    = _validate(prefix)
        used = self._used.setdefault(p, set())
        n    = max(used, default=0) + 1
        used.add(n)
        return _fmt(p, n)

    def reserve(self, full_id: str):
        p, n = _parse(_norm_id(full_id))
        if p is None: raise ValueError(f"invalid id: {full_id}")
        if n in self._used.get(p, set()): raise ValueError(f"collision: {full_id}")
        self._used.setdefault(p, set()).add(n)

    def is_used(self, full_id: str) -> bool:
        p, n = _parse(_norm_id(full_id))
        return p is not None and n in self._used.get(p, set())


def assign_ids(existing: list[dict], new_reqs: list[dict],
               prefix: str = "REQ", *, overwrite: bool = False) -> list[dict]:
    prefix   = _validate(prefix)
    registry = IDRegistry.from_existing(existing)
    needs_new, items = [], [r.copy() for r in new_reqs]

    # pass 1: 유효한 ID 먼저 전부 reserve
    for i, req in enumerate(items):
        raw = req.get("requirement_id", "").strip()
        if raw and not overwrite:
            if registry.is_used(raw):
                logger.warning("id_manager: collision '%s' → reassign", raw)
                needs_new.append(i)
            else:
                try:
                    registry.reserve(raw)
                    req["requirement_id"] = _norm_id(raw)
                except ValueError:
                    needs_new.append(i)
        else:
            needs_new.append(i)

    # pass 2: 새 ID 발급
    for i in needs_new:
        items[i]["requirement_id"] = registry.next_id(prefix)

    return items


def reindex(reqs: list[dict], prefix: str = "REQ", *, start: int = 1) -> list[dict]:
    prefix = _validate(prefix)
    result = []
    for i, r in enumerate(reqs, start):
        c = r.copy(); c["requirement_id"] = _fmt(prefix, i); result.append(c)
    return result


def _parse(raw: str):
    m = _PATTERN.match(raw)
    return (m.group(1), int(m.group(2))) if m else (None, None)

def _norm_id(raw: str) -> str:
    return raw.strip().upper()

def _validate(prefix: str) -> str:
    p = prefix.strip().upper()
    if not re.match(r"^[A-Z][A-Z0-9_]*$", p):
        raise ValueError(f"invalid prefix: {prefix}")
    return p

def _fmt(prefix: str, num: int) -> str:
    return f"{prefix}-{num:0{max(3, len(str(num)))}d}"
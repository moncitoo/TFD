"""Interpretació de rangs i números de temporada/episodi."""
import re
from typing import Optional, Tuple

Ep = Tuple[int, int]  # (temporada, episodi)

_PATTERNS = [
    # S01E05, S1 E05, S01.E05, T1 E05, T01E05
    re.compile(r"(?<![a-z0-9])[st]\s?(\d{1,2})(?:[\s._-]?e|x)\s?(\d{1,3})(?!\d)", re.I),
    # 1x05, 01x05
    re.compile(r"(?<![a-z0-9])(\d{1,2})\s?x\s?(\d{1,3})(?!\d)", re.I),
]
_RANGE = re.compile(r"^\s*(\d{1,2})x(\d{1,3})\s*-\s*(\d{1,2})x(\d{1,3})\s*$", re.I)


def parse_episode(text: str) -> Optional[Ep]:
    """Retorna (temporada, episodi) del primer patró que coincideixi."""
    for pat in _PATTERNS:
        m = pat.search(text or "")
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def parse_range(text: str) -> Tuple[Ep, Ep]:
    m = _RANGE.match(text)
    if not m:
        raise ValueError("Rang invàlid. Format esperat: 01x01-03x15")
    start, end = (int(m[1]), int(m[2])), (int(m[3]), int(m[4]))
    if start > end:
        raise ValueError("L'inici del rang és posterior al final.")
    return start, end


def in_range(ep: Ep, start: Ep, end: Ep) -> bool:
    return start <= ep <= end

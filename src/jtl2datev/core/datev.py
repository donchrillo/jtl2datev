from pathlib import Path
from typing import Iterable

from jtl2datev.core.models import LineDecision


class DatevExporter:
    def __init__(self, mandantennr: int, beraternr: int) -> None:
        self._mandantennr = mandantennr
        self._beraternr = beraternr

    def export(self, decisions: Iterable[LineDecision], out_path: Path) -> None:
        raise NotImplementedError("EXTF Buchungsstapel format pending")

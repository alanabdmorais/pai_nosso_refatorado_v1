# -*- coding: utf-8 -*-
"""
models.py — Dataclasses tipadas do pipeline.
Legenda, Palavra, Clipe e CheckpointData.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Palavra:
    """Uma palavra com sua classe morfológica."""
    texto: str
    classe: str

    def __post_init__(self) -> None:
        self.texto  = self.texto.strip()
        self.classe = self.classe.strip().lower()


@dataclass
class Legenda:
    """Um bloco SRT com timestamps em ms e lista de palavras classificadas."""
    id: int
    inicio_ms: int
    fim_ms: int
    texto: str
    palavras: list[Palavra] = field(default_factory=list)

    # ── propriedades de conveniência ──────────────────────────────────────────
    @property
    def inicio_str(self) -> str:
        return _ms_para_str(self.inicio_ms)

    @property
    def fim_str(self) -> str:
        return _ms_para_str(self.fim_ms)

    @property
    def duracao_ms(self) -> int:
        return max(0, self.fim_ms - self.inicio_ms)

    @property
    def inicio_seg(self) -> float:
        return self.inicio_ms / 1000.0

    @property
    def fim_seg(self) -> float:
        return self.fim_ms / 1000.0

    def __post_init__(self) -> None:
        self.texto = self.texto.strip()


@dataclass
class Clipe:
    """Metadados de um clipe de vídeo do Pixabay."""
    url: str
    autor: str
    indice: int
    arquivo_local: Optional[str] = None
    arquivo_pronto: Optional[str] = None
    duracao_seg: float = 5.0

    def __post_init__(self) -> None:
        if not self.autor or str(self.autor).lower() in ("nan", ""):
            self.autor = "Pixabay"


@dataclass
class CheckpointData:
    """Estado persistido de uma fase do pipeline."""
    fase: str
    timestamp: str
    metadados: dict = field(default_factory=dict)


# ── helpers internos ──────────────────────────────────────────────────────────

def _ms_para_str(ms: int) -> str:
    """Converte milissegundos para formato SRT hh:mm:ss,mmm."""
    h   = ms // 3_600_000
    m   = (ms % 3_600_000) // 60_000
    s   = (ms % 60_000) // 1_000
    mm  = ms % 1_000
    return f"{h:02d}:{m:02d}:{s:02d},{mm:03d}"


def str_para_ms(ts: str) -> int:
    """Converte timestamp SRT hh:mm:ss,mmm (ou .mmm) para milissegundos."""
    ts = ts.strip().replace(".", ",")
    partes = ts.split(":")
    if len(partes) != 3:
        return 0
    h, m, resto = partes
    s, mm = resto.split(",")
    return (int(h) * 3_600_000
            + int(m) * 60_000
            + int(s) * 1_000
            + int(mm))

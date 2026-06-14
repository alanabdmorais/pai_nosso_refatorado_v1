# -*- coding: utf-8 -*-
"""
checkpoint.py — Sistema de checkpoint por fase do pipeline.

Salva o estado após cada fase bem-sucedida em checkpoint.json.
Permite retomar de qualquer fase sem repetir trabalho anterior.

Uso:
    cp = Checkpoint()
    cp.salvar("audio_gerado", {"arquivo": "pai_nosso_audio.wav"})

    if cp.fase_concluida("audio_gerado"):
        print("Pulando geração de áudio...")

    cp.reiniciar_de("srt_traduzidos")  # apaga fases posteriores
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from constants import FASES_PIPELINE

logger = logging.getLogger(__name__)

ARQUIVO_CHECKPOINT = Path("checkpoint.json")


class Checkpoint:
    """Gerencia o estado persistido do pipeline em disco."""

    def __init__(self, caminho: Path = ARQUIVO_CHECKPOINT) -> None:
        self._caminho = caminho
        self._dados: dict[str, dict] = {}
        self._carregar()

    # ── Leitura ───────────────────────────────────────────────────────────────

    def _carregar(self) -> None:
        """Carrega checkpoint do disco, se existir."""
        if self._caminho.exists():
            try:
                with open(self._caminho, "r", encoding="utf-8") as fh:
                    self._dados = json.load(fh)
                logger.debug("Checkpoint carregado: %s", self._caminho)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Checkpoint corrompido, iniciando do zero: %s", exc)
                self._dados = {}

    def fase_concluida(self, fase: str) -> bool:
        """Retorna True se a fase foi concluída com sucesso."""
        return fase in self._dados and self._dados[fase].get("ok", False)

    def metadados(self, fase: str) -> dict:
        """Retorna os metadados salvos para uma fase (ou {} se não existe)."""
        return self._dados.get(fase, {}).get("metadados", {})

    def fases_concluidas(self) -> list[str]:
        """Lista todas as fases já concluídas, na ordem do pipeline."""
        return [f for f in FASES_PIPELINE if self.fase_concluida(f)]

    def proxima_fase_pendente(self) -> Optional[str]:
        """Retorna o nome da próxima fase que ainda não foi concluída."""
        for fase in FASES_PIPELINE:
            if not self.fase_concluida(fase):
                return fase
        return None  # tudo concluído

    def indice_fase(self, fase: str) -> int:
        """Retorna o índice de uma fase na lista FASES_PIPELINE (-1 se não existe)."""
        try:
            return FASES_PIPELINE.index(fase)
        except ValueError:
            return -1

    # ── Escrita ───────────────────────────────────────────────────────────────

    def salvar(self, fase: str, metadados: dict | None = None) -> None:
        """
        Marca uma fase como concluída e persiste no disco.

        Args:
            fase:      Nome da fase (deve estar em FASES_PIPELINE).
            metadados: Dados extras a associar à fase (caminhos, contagens etc.)
        """
        if fase not in FASES_PIPELINE:
            logger.warning("Fase desconhecida: '%s' — salvando mesmo assim", fase)

        self._dados[fase] = {
            "ok":        True,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "metadados": metadados or {},
        }
        self._persistir()
        logger.info("✅ Checkpoint salvo: %s", fase)

    def marcar_falha(self, fase: str, erro: str) -> None:
        """Registra uma falha em uma fase (não marca como concluída)."""
        self._dados[fase] = {
            "ok":        False,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "erro":      erro,
            "metadados": {},
        }
        self._persistir()
        logger.warning("❌ Checkpoint de falha: %s — %s", fase, erro)

    def reiniciar_de(self, fase: str) -> None:
        """
        Apaga do checkpoint todas as fases a partir de `fase` (inclusive).
        Útil para forçar reprocessamento de um estágio e os seguintes.
        """
        idx = self.indice_fase(fase)
        if idx == -1:
            raise ValueError(f"Fase desconhecida: '{fase}'")

        fases_a_apagar = FASES_PIPELINE[idx:]
        for f in fases_a_apagar:
            self._dados.pop(f, None)

        self._persistir()
        logger.info("🔄 Checkpoint reiniciado a partir de '%s'", fase)

    def resetar_tudo(self) -> None:
        """Apaga todo o checkpoint (começa do zero)."""
        self._dados = {}
        self._persistir()
        logger.info("🗑️ Checkpoint completamente resetado")

    # ── Internos ──────────────────────────────────────────────────────────────

    def _persistir(self) -> None:
        """Grava self._dados no disco de forma atômica."""
        tmp = self._caminho.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self._dados, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, self._caminho)

    # ── Relatório ─────────────────────────────────────────────────────────────

    def resumo(self) -> str:
        """Retorna string legível com o estado de todas as fases."""
        linhas = ["── Checkpoint ──────────────────────────────"]
        for fase in FASES_PIPELINE:
            if fase not in self._dados:
                status = "⬜ pendente"
            elif self._dados[fase].get("ok"):
                ts = self._dados[fase].get("timestamp", "")
                status = f"✅ concluído  [{ts}]"
            else:
                erro = self._dados[fase].get("erro", "?")[:60]
                status = f"❌ falhou     [{erro}]"
            linhas.append(f"  {fase:<28} {status}")
        linhas.append("────────────────────────────────────────────")
        return "\n".join(linhas)

    def __repr__(self) -> str:
        concluidas = len(self.fases_concluidas())
        return f"<Checkpoint {concluidas}/{len(FASES_PIPELINE)} fases em '{self._caminho}'>"

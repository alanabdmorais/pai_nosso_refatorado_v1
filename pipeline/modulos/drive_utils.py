# -*- coding: utf-8 -*-
"""
drive_utils.py — Utilitários para Google Drive.

Fornece um DriveClient singleton que opera sobre o Drive MONTADO em
/content/drive/MyDrive (drive.mount() já feito na Célula 0 do notebook).

Em vez de IDs de pasta + API REST, as operações são feitas por
caminho de pasta dentro da estrutura `assets/` do projeto
(ver PipelineConfig.pasta_assets_*).

Uso:
    from drive_utils import DriveClient
    drive = DriveClient.get()
    drive.upload("arquivo.mp4", cfg.pasta_assets_videos, "video/mp4")
    drive.download(cfg.pasta_assets_videos, "arquivo.mp4", "destino.mp4")
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DriveError(Exception):
    """Erro nas operações do Google Drive."""


class DriveClient:
    """
    Wrapper sobre o Drive montado (path-based).
    Padrão singleton — use DriveClient.get() para obter a instância.

    As pastas de destino são caminhos dentro de /content/drive/MyDrive/
    (normalmente subpastas de assets/, ver PipelineConfig).
    """

    _instance: Optional["DriveClient"] = None

    def __init__(self) -> None:
        pass

    # ── Singleton ─────────────────────────────────────────────────────────────

    @classmethod
    def get(cls) -> "DriveClient":
        """Retorna (e cria se necessário) a instância singleton."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Upload ────────────────────────────────────────────────────────────────

    def upload(
        self,
        arquivo_local: Path | str,
        pasta_destino: Path | str,
        mimetype: str = "application/octet-stream",
        substituir: bool = True,
    ) -> str:
        """
        Copia um arquivo local para uma pasta do Drive montado.

        Args:
            arquivo_local: Caminho local do arquivo.
            pasta_destino: Pasta de destino no Drive montado (ex: cfg.pasta_assets_audio).
            mimetype:      Tipo MIME do arquivo (mantido por compatibilidade, não usado).
            substituir:    Se True, sobrescreve versão anterior com o mesmo nome.

        Returns:
            Caminho (str) do arquivo no Drive.
        """
        arquivo_local = Path(arquivo_local)
        pasta_destino = Path(pasta_destino)

        if not arquivo_local.exists():
            raise DriveError(f"Arquivo não encontrado para upload: {arquivo_local}")

        try:
            pasta_destino.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            raise DriveError(f"Falha ao criar pasta '{pasta_destino}': {exc}") from exc

        destino = pasta_destino / arquivo_local.name

        if destino.exists() and not substituir:
            logger.debug("   ⏭️  Já existe e substituir=False: %s", destino)
            return str(destino)

        tamanho_mb = arquivo_local.stat().st_size / 1_048_576
        logger.info("📤 Upload: %s (%.2f MB) → %s", arquivo_local.name, tamanho_mb, pasta_destino)

        try:
            shutil.copy2(arquivo_local, destino)
            logger.info("   ✅ Salvo no Drive: %s", destino)
            return str(destino)
        except Exception as exc:
            raise DriveError(f"Falha no upload de '{arquivo_local.name}': {exc}") from exc

    # ── Download ──────────────────────────────────────────────────────────────

    def download(
        self,
        pasta_origem: Path | str,
        nome_arquivo: str,
        destino: Path | str,
    ) -> bool:
        """
        Copia um arquivo de uma pasta do Drive montado para o destino local.

        Returns:
            True se copiou com sucesso, False se o arquivo não foi encontrado.
        """
        pasta_origem = Path(pasta_origem)
        destino = Path(destino)
        origem = pasta_origem / nome_arquivo

        if not origem.exists():
            logger.warning("   ⚠️ Arquivo não encontrado no Drive: %s", origem)
            return False

        logger.info("📥 Download: %s → %s", origem, destino)
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origem, destino)
            logger.info("   ✅ Baixado: %s", nome_arquivo)
            return True
        except Exception as exc:
            raise DriveError(f"Falha no download de '{nome_arquivo}': {exc}") from exc

    def download_se_ausente(
        self,
        pasta_origem: Path | str,
        nome_arquivo: str,
        destino: Path | str,
    ) -> bool:
        """
        Copia apenas se o arquivo não existir localmente.
        Retorna True se está disponível localmente (copiado agora ou já existia).
        """
        destino = Path(destino)
        if destino.exists():
            logger.debug("   ✅ %s já existe localmente", nome_arquivo)
            return True
        return self.download(pasta_origem, nome_arquivo, destino)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def listar_pasta(self, pasta: Path | str) -> list[dict]:
        """Lista arquivos de uma pasta do Drive montado. Retorna lista de dicts {id, name}."""
        pasta = Path(pasta)
        if not pasta.exists():
            return []
        try:
            return [
                {"id": str(p), "name": p.name, "mimeType": "", "size": p.stat().st_size}
                for p in pasta.iterdir()
                if p.is_file()
            ]
        except Exception as exc:
            raise DriveError(f"Erro ao listar pasta {pasta}: {exc}") from exc

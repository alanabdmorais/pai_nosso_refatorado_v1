# -*- coding: utf-8 -*-
"""
drive_utils.py — Utilitários para Google Drive.

Fornece um DriveClient singleton: autentica uma única vez e reutiliza
o service em todas as operações do pipeline.

Uso:
    from drive_utils import DriveClient
    drive = DriveClient.get()
    drive.upload("arquivo.mp4", pasta_id, "video/mp4")
    drive.download(pasta_id, "arquivo.mp4", "destino.mp4")
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Imports do Google são feitos sob demanda para não quebrar em ambientes
# sem o SDK instalado durante testes locais.
_service = None


class DriveError(Exception):
    """Erro nas operações do Google Drive."""


class DriveClient:
    """
    Wrapper sobre a API do Google Drive com autenticação lazy.
    Padrão singleton — use DriveClient.get() para obter a instância.
    """

    _instance: Optional["DriveClient"] = None

    def __init__(self) -> None:
        self._service = None

    # ── Singleton ─────────────────────────────────────────────────────────────

    @classmethod
    def get(cls) -> "DriveClient":
        """Retorna (e cria se necessário) a instância singleton."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Autenticação ──────────────────────────────────────────────────────────

    def _ensure_service(self):
        """Autentica no Drive se ainda não autenticado. Reutiliza em chamadas seguintes."""
        if self._service is not None:
            return self._service

        try:
            from google.colab import auth
            from googleapiclient.discovery import build

            auth.authenticate_user()
            self._service = build("drive", "v3")
            logger.info("✅ Drive autenticado")
        except Exception as exc:
            raise DriveError(f"Falha na autenticação do Drive: {exc}") from exc

        return self._service

    # ── Upload ────────────────────────────────────────────────────────────────

    def upload(
        self,
        arquivo_local: Path | str,
        pasta_id: str,
        mimetype: str = "application/octet-stream",
        substituir: bool = True,
    ) -> str:
        """
        Faz upload de um arquivo para o Drive.

        Args:
            arquivo_local: Caminho local do arquivo.
            pasta_id:      ID da pasta de destino no Drive.
            mimetype:      Tipo MIME do arquivo.
            substituir:    Se True, remove versão anterior com o mesmo nome.

        Returns:
            ID do arquivo no Drive.
        """
        from googleapiclient.http import MediaFileUpload

        arquivo_local = Path(arquivo_local)
        if not arquivo_local.exists():
            raise DriveError(f"Arquivo não encontrado para upload: {arquivo_local}")

        service = self._ensure_service()
        nome    = arquivo_local.name

        if substituir:
            self._remover_existente(pasta_id, nome)

        tamanho_mb = arquivo_local.stat().st_size / 1_048_576
        logger.info("📤 Upload: %s (%.2f MB) → Drive/%s", nome, tamanho_mb, pasta_id[:8])

        media    = MediaFileUpload(str(arquivo_local), mimetype=mimetype, resumable=True)
        metadata = {"name": nome, "parents": [pasta_id]}

        try:
            resultado = service.files().create(
                body=metadata, media_body=media, fields="id"
            ).execute()
            file_id = resultado.get("id")
            logger.info("   ✅ Salvo no Drive (ID: %s)", file_id)
            return file_id
        except Exception as exc:
            raise DriveError(f"Falha no upload de '{nome}': {exc}") from exc

    # ── Download ──────────────────────────────────────────────────────────────

    def download(
        self,
        pasta_id: str,
        nome_arquivo: str,
        destino: Path | str,
    ) -> bool:
        """
        Baixa um arquivo do Drive pelo nome.

        Returns:
            True se baixou com sucesso, False se o arquivo não foi encontrado.
        """
        from googleapiclient.http import MediaIoBaseDownload

        service = self._ensure_service()
        destino = Path(destino)

        file_id = self._buscar_id(pasta_id, nome_arquivo)
        if not file_id:
            logger.warning("   ⚠️ Arquivo não encontrado no Drive: %s", nome_arquivo)
            return False

        logger.info("📥 Download: %s → %s", nome_arquivo, destino)
        try:
            request    = service.files().get_media(fileId=file_id)
            fh         = io.FileIO(str(destino), "wb")
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            fh.close()
            logger.info("   ✅ Baixado: %s", nome_arquivo)
            return True
        except Exception as exc:
            raise DriveError(f"Falha no download de '{nome_arquivo}': {exc}") from exc

    def download_se_ausente(
        self,
        pasta_id: str,
        nome_arquivo: str,
        destino: Path | str,
    ) -> bool:
        """
        Baixa apenas se o arquivo não existir localmente.
        Retorna True se está disponível localmente (baixado agora ou já existia).
        """
        destino = Path(destino)
        if destino.exists():
            logger.debug("   ✅ %s já existe localmente", nome_arquivo)
            return True
        return self.download(pasta_id, nome_arquivo, destino)

    # ── Helpers internos ──────────────────────────────────────────────────────

    def _buscar_id(self, pasta_id: str, nome: str) -> Optional[str]:
        """Retorna o Drive ID do arquivo pelo nome na pasta, ou None."""
        service = self._ensure_service()
        query   = (
            f"'{pasta_id}' in parents "
            f"and name = '{nome}' "
            f"and trashed = false"
        )
        try:
            results = service.files().list(
                q=query, fields="files(id, name)"
            ).execute()
            items = results.get("files", [])
            return items[0]["id"] if items else None
        except Exception as exc:
            logger.warning("Erro ao buscar '%s' no Drive: %s", nome, exc)
            return None

    def _remover_existente(self, pasta_id: str, nome: str) -> None:
        """Remove arquivo(s) com o mesmo nome na pasta do Drive."""
        service = self._ensure_service()
        query   = (
            f"'{pasta_id}' in parents "
            f"and name = '{nome}' "
            f"and trashed = false"
        )
        try:
            results = service.files().list(
                q=query, fields="files(id, name)"
            ).execute()
            for item in results.get("files", []):
                service.files().delete(fileId=item["id"]).execute()
                logger.debug("   🗑️ Removido do Drive: %s (ID: %s)", nome, item["id"])
        except Exception as exc:
            logger.warning("Erro ao remover '%s' do Drive: %s", nome, exc)

    def listar_pasta(self, pasta_id: str) -> list[dict]:
        """Lista arquivos de uma pasta. Retorna lista de dicts {id, name}."""
        service = self._ensure_service()
        query   = f"'{pasta_id}' in parents and trashed = false"
        try:
            results = service.files().list(
                q=query, fields="files(id, name, mimeType, size)"
            ).execute()
            return results.get("files", [])
        except Exception as exc:
            raise DriveError(f"Erro ao listar pasta {pasta_id}: {exc}") from exc

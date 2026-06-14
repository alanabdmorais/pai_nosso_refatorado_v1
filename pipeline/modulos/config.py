# -*- coding: utf-8 -*-
"""
config.py — Configuração centralizada do pipeline.
Para trocar a oração: altere NOME_ORACAO e TEXTO_ORACAO.
Todos os nomes de arquivo e pastas são derivados automaticamente.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from constants import (
    IDIOMAS, SIGLAS_IDIOMAS, POSICOES_Y, POS_SIGLA_Y,
    CORES_HTML, TEXTO_PRETO, LARGURA_TELA, ALTURA_TELA,
    TAMANHO_FONTE_TAG, TAMANHO_FONTE_SIGLA, BOX_BORDER,
    ESPACAMENTO_PALAVRA, LARGURA_CHAR,
)

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """
    Configuração completa do pipeline.

    Campos obrigatórios a ajustar por oração:
        NOME_ORACAO   — identificador curto (ex: 'pai_nosso', 'ave_maria')
        TEXTO_ORACAO  — texto completo para o TTS
        VOZ_EDGE      — voz do Edge TTS

    IDs do Google Drive: pastas já existentes no seu Drive.
    As pastas de correções/brutos são criadas automaticamente pelo Classifier.
    """

    # ── Identidade da oração ──────────────────────────────────────────────────
    NOME_ORACAO: str = "pai_nosso"
    TEXTO_ORACAO: str = (
        "Pai Nosso que estais no céu,\n"
        "santificado seja o vosso nome.\n"
        "Venha a nós o vosso reino.\n"
        "Seja feita a vossa vontade,\n"
        "assim na terra como no céu.\n"
        "O pão nosso de cada dia nos dai hoje.\n"
        "Perdoai as nossas ofensas,\n"
        "assim como nós perdoamos a quem nos tem ofendido.\n"
        "E não nos deixeis cair em tentação,\n"
        "mas livrai-nos do mal. Amém."
    )

    # ── Voz e idiomas ─────────────────────────────────────────────────────────
    VOZ_EDGE: str = "pt-BR-AntonioNeural"
    IDIOMAS: list[str] = field(default_factory=lambda: IDIOMAS.copy())

    # ── IDs do Google Drive (pastas existentes) ───────────────────────────────
    ID_PLANILHA_DRIVE:      str = "1bF7hnGSY7AALm4ZAS5owWNpiSTdgArW4ahAuVZaHPL0"
    ID_PASTA_AUDIO:         str = "1ZkEf6L6ZU0slgb-3QIhszWgu5A15v3rp"
    ID_PASTA_LEGENDAS:      str = "1X3aYPgrGvmUa_o57wksJs9AqkigZ7RNe"
    ID_PASTA_CLASSIFICACAO: str = "143trJsd-DNTTNoZzbUigO4LAXxQpWSMF"
    ID_PASTA_LOGO:          str = "1ANVbsVrFLugX5Z4wWZZ6ZdJZ-nk_CapO"
    ID_PASTA_MUSICA:        str = "1Ti_BxaT6HZ_dk84pRNUqHyRDJDb1ee_3"
    ID_PASTA_VIDEOS:        str = "1VR0dneES_DJxRX6jupeQHmC05ouLWV1e"
    ID_PASTA_COOKIES:       str = "1ZuxVr-pofA-Naqo8ysfGxWpYjSaSt3aE"

    # ── Assets externos ───────────────────────────────────────────────────────
    NOME_ARQUIVO_LOGO:   str = "globo_cruz_logo.png"
    NOME_ARQUIVO_MUSICA: str = (
        "Calmo créditos Shattered Paths - Aakash Gandhi(Youtube Audio Library).mp3"
    )
    NOME_COOKIES: str = "cookies.txt"

    # ── Parâmetros de vídeo ───────────────────────────────────────────────────
    DURACAO_CLIPE:   int   = 5
    TAMANHO_LOGO:    int   = 80
    VOLUME_MUSICA:   float = 0.25
    GROQ_MODEL:      str   = "llama-3.3-70b-versatile"

    # ── Layout de legenda ─────────────────────────────────────────────────────
    POSICOES_Y:          dict[str, int] = field(default_factory=lambda: POSICOES_Y.copy())
    POS_SIGLA_Y:         dict[str, int] = field(default_factory=lambda: POS_SIGLA_Y.copy())
    SIGLAS_IDIOMAS:      dict[str, str] = field(default_factory=lambda: SIGLAS_IDIOMAS.copy())
    CORES_HTML:          dict[str, str] = field(default_factory=lambda: CORES_HTML.copy())
    TEXTO_PRETO:         set[str]       = field(default_factory=lambda: TEXTO_PRETO.copy())
    LARGURA_TELA:        int = LARGURA_TELA
    ALTURA_TELA:         int = ALTURA_TELA
    TAMANHO_FONTE_TAG:   int = TAMANHO_FONTE_TAG
    TAMANHO_FONTE_SIGLA: int = TAMANHO_FONTE_SIGLA
    BOX_BORDER:          int = BOX_BORDER
    ESPACAMENTO_PALAVRA: int = ESPACAMENTO_PALAVRA
    LARGURA_CHAR:        int = LARGURA_CHAR

    # ── Modo de geração de vídeo ─────────────────────────────────────────────
    VIDEO_SIMPLES_SEM_MORFOLOGIA: bool = False
    # False (padrão) = vídeo completo com cores por palavra (classificação morfológica)
    # True           = vídeo simples com cor sólida por idioma (sem classificação)

    # ── Retry / performance ───────────────────────────────────────────────────
    GROQ_MAX_TENTATIVAS:    int   = 3
    GROQ_DELAY_ENTRE_CALLS: float = 2.0
    DOWNLOAD_TIMEOUT:       int   = 30
    FFMPEG_NUM_THREADS:     int   = 3

    # ── Nomes de arquivo derivados ────────────────────────────────────────────

    @property
    def NOME_AUDIO(self) -> str:
        return f"{self.NOME_ORACAO}_audio.wav"

    @property
    def NOME_VIDEO_BASE(self) -> str:
        return f"{self.NOME_ORACAO}_base.mp4"

    @property
    def NOME_VIDEO_FINAL(self) -> str:
        return f"{self.NOME_ORACAO}_final.mp4"

    @property
    def NOME_SRT_PT_EDGE(self) -> str:
        return f"{self.NOME_ORACAO}_pt_edge.srt"

    @property
    def NOME_SRT_PT(self) -> str:
        return f"{self.NOME_ORACAO}_pt.srt"

    def nome_srt(self, lang: str) -> str:
        return f"{self.NOME_ORACAO}_{lang}.srt"

    def nome_classificacao(self, lang: str) -> str:
        return f"classificacao_{self.NOME_ORACAO}_{lang}.json"

    def nome_ass(self, lang: str) -> str:
        return f"legendas_{self.NOME_ORACAO}_{lang}.ass"

    # ── Pastas do Drive (caminhos de path, não IDs — para acesso direto) ─────

    @property
    def pasta_drive_correcoes(self) -> Path:
        """Onde o usuário coloca os JSONs revisados pela IA."""
        return Path(f"/content/drive/MyDrive/pai_nosso_refatorado_v1/pipeline/correcoes/{self.NOME_ORACAO}")

    @property
    def pasta_drive_brutos(self) -> Path:
        """Onde o pipeline salva os JSONs brutos gerados pelo Groq."""
        return Path(f"/content/drive/MyDrive/pai_nosso_refatorado_v1/pipeline/brutos/{self.NOME_ORACAO}")

    # ── Validação ─────────────────────────────────────────────────────────────

    def validate(self) -> None:
        erros: list[str] = []
        if not self.NOME_ORACAO:
            erros.append("NOME_ORACAO não pode ser vazio")
        if not self.TEXTO_ORACAO:
            erros.append("TEXTO_ORACAO não pode ser vazio")
        for id_attr in ["ID_PLANILHA_DRIVE", "ID_PASTA_AUDIO", "ID_PASTA_LEGENDAS",
                        "ID_PASTA_CLASSIFICACAO", "ID_PASTA_VIDEOS"]:
            if not getattr(self, id_attr):
                erros.append(f"{id_attr} não configurado")
        if erros:
            raise ValueError("PipelineConfig inválido:\n" + "\n".join(f"  - {e}" for e in erros))
        logger.info("PipelineConfig OK: '%s'", self.NOME_ORACAO)

    def resumo(self) -> str:
        return "\n".join([
            f"Oração:        {self.NOME_ORACAO}",
            f"Áudio:         {self.NOME_AUDIO}",
            f"SRT mestre:    {self.NOME_SRT_PT}",
            f"Vídeo final:   {self.NOME_VIDEO_FINAL}",
            f"Idiomas:       {', '.join(self.IDIOMAS)}",
            f"Voz Edge TTS:  {self.VOZ_EDGE}",
            f"Modelo Groq:   {self.GROQ_MODEL}",
            f"Duração clipe: {self.DURACAO_CLIPE}s",
            f"Correcoes:     {self.pasta_drive_correcoes}",
            f"Brutos:        {self.pasta_drive_brutos}",
            f"Modo simples:  {'SIM (sem morfologia)' if self.VIDEO_SIMPLES_SEM_MORFOLOGIA else 'NÃO (completo)'}",
        ])

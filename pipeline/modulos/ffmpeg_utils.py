# -*- coding: utf-8 -*-
"""
ffmpeg_utils.py — Operações FFmpeg e geração de subtítulos ASS.

A otimização crítica deste módulo é a função gerar_ass():
em vez de centenas de filtros drawtext (um por palavra), geramos
um único arquivo .ass por idioma e usamos -vf "ass=arquivo.ass".
Isso reduz o tempo de render em ~10×.

Funções principais:
    cortar_video(entrada, saida, duracao)
    concatenar_videos(lista, saida)
    adicionar_credito_e_logo(video, saida, credito, logo, tamanho)
    adicionar_audio(video, audio, saida)
    adicionar_trilha_fundo(video, musica, saida, volume)
    gerar_ass(legendas_por_idioma, config)     → Path   ← CRÍTICO
    queimar_legendas_ass(video, ass_path, saida)
    obter_duracao(arquivo)                     → float
"""
from __future__ import annotations

import logging
import os
import subprocess
import unicodedata
from pathlib import Path
from typing import Optional

from config import PipelineConfig
from models import Legenda
from constants import CORES_HTML, TEXTO_PRETO, SIGLAS_IDIOMAS

logger = logging.getLogger(__name__)


class FFmpegError(Exception):
    """Erro nas operações do FFmpeg."""


# ── Helpers internos ──────────────────────────────────────────────────────────

def _run(cmd: list[str], descricao: str = "") -> subprocess.CompletedProcess:
    """Executa um comando FFmpeg e lança FFmpegError se falhar."""
    logger.debug("FFmpeg: %s", " ".join(cmd[:6]) + " ...")
    resultado = subprocess.run(cmd, capture_output=True, text=True)
    if resultado.returncode != 0:
        stderr = resultado.stderr[-600:] if resultado.stderr else "(sem stderr)"
        raise FFmpegError(
            f"FFmpeg falhou ({descricao or cmd[1]}):\n{stderr}"
        )
    return resultado


def _escapar(texto: str) -> str:
    """
    Remove acentos e caracteres especiais para uso seguro em filtros FFmpeg.
    Necessário pois drawtext/ASS têm limitações de encoding.
    """
    sem_acento = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode("ascii")
    # remove caracteres que quebram o filtro drawtext
    return sem_acento.replace("'", "").replace('"', "").replace(":", "").replace("\\", "")


def _ms_para_ass(ms: int) -> str:
    """Converte milissegundos para timestamp ASS (h:mm:ss.cc — centésimos)."""
    h  = ms // 3_600_000
    m  = (ms % 3_600_000) // 60_000
    s  = (ms % 60_000) // 1_000
    cc = (ms % 1_000) // 10
    return f"{h}:{m:02d}:{s:02d}.{cc:02d}"


def _html_para_ass_cor(html_hex: str) -> str:
    """Converte #RRGGBB ou 0xRRGGBB para formato ASS &H00BBGGRR."""
    h = html_hex.replace("#", "").replace("0x", "").upper().zfill(6)
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}"


def _cor_texto_ass(classe: str) -> str:
    """Retorna cor ASS do texto (preto ou branco) conforme o fundo."""
    if classe in TEXTO_PRETO:
        return "&H00000000"   # preto opaco
    return "&H00FFFFFF"       # branco opaco


# ── Operações básicas de vídeo ────────────────────────────────────────────────

def obter_duracao(arquivo: Path | str) -> float:
    """Retorna a duração do arquivo de mídia em segundos."""
    resultado = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(arquivo),
        ],
        capture_output=True, text=True,
    )
    try:
        return float(resultado.stdout.strip())
    except ValueError:
        return 0.0


def cortar_video(
    entrada: Path | str,
    saida:   Path | str,
    duracao: float,
) -> Path:
    """Corta os primeiros `duracao` segundos do vídeo (stream copy — sem reencoding)."""
    saida = Path(saida)
    _run(
        ["ffmpeg", "-y", "-i", str(entrada),
         "-t", str(duracao), "-c", "copy", str(saida)],
        "cortar_video",
    )
    logger.debug("cortar_video: %s → %s (%.1fs)", Path(entrada).name, saida.name, duracao)
    return saida


def concatenar_videos(lista_arquivos: list[Path | str], saida: Path | str) -> Path:
    """Concatena vídeos usando o demuxer concat do FFmpeg (stream copy)."""
    saida     = Path(saida)
    lista_txt = saida.with_suffix(".txt")

    with open(lista_txt, "w", encoding="utf-8") as fh:
        for arq in lista_arquivos:
            fh.write(f"file '{arq}'\n")

    _run(
        ["ffmpeg", "-y",
         "-f", "concat", "-safe", "0", "-i", str(lista_txt),
         "-c", "copy", str(saida)],
        "concatenar_videos",
    )
    lista_txt.unlink(missing_ok=True)
    logger.info("concatenar_videos: %d clipes → %s", len(lista_arquivos), saida.name)
    return saida


def adicionar_credito_e_logo(
    video_entrada: Path | str,
    saida:         Path | str,
    texto_credito: str,
    logo_path:     Optional[Path | str],
    tamanho_logo:  int = 80,
) -> Path:
    """
    Adiciona crédito de texto (canto inferior esquerdo) e logo (canto inferior direito).
    Combina tudo em um único passe FFmpeg.
    """
    saida         = Path(saida)
    credito_safe  = _escapar(texto_credito)

    filtro_credito = (
        f"drawtext=text='{credito_safe}':"
        f"fontcolor=white:fontsize=16:"
        f"x=10:y=h-30:"
        f"box=1:boxcolor=black@0.5:boxborderw=5"
    )

    if logo_path and Path(logo_path).exists():
        filtro_combo = (
            f"[0:v]{filtro_credito}[tmp];"
            f"[1:v]scale={tamanho_logo}:-1[logo];"
            f"[tmp][logo]overlay=W-w-0:H-h-0"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_entrada),
            "-i", str(logo_path),
            "-filter_complex", filtro_combo,
            "-c:a", "copy", "-c:v", "libx264",
            "-preset", "ultrafast", "-crf", "28",
            str(saida),
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_entrada),
            "-vf", filtro_credito,
            "-c:a", "copy", "-c:v", "libx264",
            "-preset", "ultrafast", "-crf", "28",
            str(saida),
        ]

    _run(cmd, "credito_e_logo")
    logger.info("adicionar_credito_e_logo: %s", saida.name)
    return saida


def adicionar_audio(
    video_entrada: Path | str,
    audio_entrada: Path | str,
    saida:         Path | str,
) -> Path:
    """Adiciona faixa de áudio ao vídeo (substitui qualquer áudio existente)."""
    saida = Path(saida)
    _run(
        ["ffmpeg", "-y",
         "-i", str(video_entrada), "-i", str(audio_entrada),
         "-c:v", "copy", "-c:a", "aac",
         "-map", "0:v:0", "-map", "1:a:0",
         "-shortest", "-af", "aresample=async=1",
         str(saida)],
        "adicionar_audio",
    )
    logger.info("adicionar_audio: %s + %s → %s",
                Path(video_entrada).name, Path(audio_entrada).name, saida.name)
    return saida


def adicionar_trilha_fundo(
    video_entrada: Path | str,
    musica:        Path | str,
    saida:         Path | str,
    volume:        float = 0.25,
) -> Path:
    """
    Mistura a trilha de fundo à narração já presente no vídeo.
    A música é reduzida de volume e recortada/repetida para cobrir o vídeo.
    """
    saida = Path(saida)
    filtro = (
        f"[1:a]volume={volume},aloop=loop=-1:size=2e+09[bg];"
        f"[0:a][bg]amix=inputs=2:duration=first[a]"
    )
    _run(
        ["ffmpeg", "-y",
         "-i", str(video_entrada), "-i", str(musica),
         "-filter_complex", filtro,
         "-map", "0:v", "-map", "[a]",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-shortest", str(saida)],
        "trilha_fundo",
    )
    logger.info("adicionar_trilha_fundo: volume=%.0f%% → %s", volume * 100, saida.name)
    return saida


# ── Geração de ASS ─────────────────────────────────────────────────────────────

# Cabeçalho de um arquivo .ass com uma única seção de estilos
_ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: {largura}
PlayResY: {altura}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{tamanho_fonte},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

# Template de uma linha de diálogo ASS para palavra colorida
# Usa tags override: {\1c&HColor&\3c&HBorderColor&} por palavra
_LINHA_DIALOGO = "Dialogue: 0,{inicio},{fim},Default,,0,0,0,,{texto}\n"


def gerar_ass(
    legendas_por_idioma: dict[str, list[Legenda]],
    config: PipelineConfig,
    caminho_saida: Optional[Path | str] = None,
) -> Path:
    """
    Gera um único arquivo .ass com as legendas coloridas de TODOS os idiomas.

    Cada palavra recebe um box colorido usando tags override ASS:
      {\\1c&HCOR&\\bord4\\shad0\\p0} palavra {\\r}

    Todos os 4 idiomas ficam em posições Y diferentes no mesmo arquivo,
    eliminando a necessidade de múltiplos passes de render.

    Args:
        legendas_por_idioma: dict { "pt": [...], "en": [...], ... }
        config:              PipelineConfig com posições, cores, etc.
        caminho_saida:       Caminho do .ass (default: legendas_{NOME}.ass)

    Returns:
        Path do arquivo .ass gerado.
    """
    if caminho_saida is None:
        caminho_saida = Path(f"legendas_{config.NOME_ORACAO}.ass")
    else:
        caminho_saida = Path(caminho_saida)

    linhas: list[str] = [
        _ASS_HEADER.format(
            largura=config.LARGURA_TELA,
            altura=config.ALTURA_TELA,
            tamanho_fonte=config.TAMANHO_FONTE_TAG,
        )
    ]

    # ── siglas de idioma (sempre visíveis, sem box colorido) ──────────────────
    for lang, legendas in legendas_por_idioma.items():
        if not legendas:
            continue
        sigla   = config.SIGLAS_IDIOMAS.get(lang, lang.upper())
        y_sigla = config.POS_SIGLA_Y.get(lang, 50)
        fim_total_ms = max(leg.fim_ms for leg in legendas) + 500

        # posição Y em ASS: MarginV controla distância da borda inferior
        # com Alignment=2 (centro-baixo), MarginV é medido de baixo para cima
        margem_v = config.ALTURA_TELA - y_sigla

        inicio_ass = _ms_para_ass(0)
        fim_ass    = _ms_para_ass(fim_total_ms)
        texto_ass  = (
            f"{{\\an2\\pos({config.LARGURA_TELA // 2},{y_sigla})"
            f"\\1c&H808080&\\bord4\\shad0\\fs{config.TAMANHO_FONTE_SIGLA}}}"
            f"{sigla}"
        )
        linhas.append(_LINHA_DIALOGO.format(
            inicio=inicio_ass, fim=fim_ass, texto=texto_ass
        ))

    # ── palavras coloridas ────────────────────────────────────────────────────
    for lang, legendas in legendas_por_idioma.items():
        y_base = config.POS_SIGLA_Y.get(lang, 100)
        # calcula Y das palavras: abaixo da sigla
        y_palavras = config.POSICOES_Y.get(lang, y_base + 35)

        for leg in legendas:
            if not leg.palavras:
                # legenda sem classificação: renderiza texto plano
                _adicionar_linha_simples(linhas, leg, y_palavras, config)
                continue

            _adicionar_linha_colorida(linhas, leg, y_palavras, config)

    caminho_saida.write_text("".join(linhas), encoding="utf-8-sig")
    logger.info("gerar_ass: %s (%d linhas)", caminho_saida.name, len(linhas))
    return caminho_saida


def _adicionar_linha_simples(
    linhas: list[str],
    leg: Legenda,
    y: int,
    config: PipelineConfig,
) -> None:
    """Adiciona linha ASS com o texto da legenda sem colorização por palavra."""
    texto_safe = _escapar(leg.texto)
    texto_ass  = (
        f"{{\\an2\\pos({config.LARGURA_TELA // 2},{y})"
        f"\\1c&H00FFFFFF&\\bord4\\shad0}}"
        f"{texto_safe}"
    )
    linhas.append(_LINHA_DIALOGO.format(
        inicio=_ms_para_ass(leg.inicio_ms),
        fim   =_ms_para_ass(leg.fim_ms),
        texto =texto_ass,
    ))


def _adicionar_linha_colorida(
    linhas: list[str],
    leg: Legenda,
    y: int,
    config: PipelineConfig,
) -> None:
    """
    Adiciona linha ASS com cada palavra em sua cor morfológica.

    Usa a tag \\pos() para centralizar o bloco inteiro,
    e tags override {\\1c} por palavra para mudar a cor individualmente.

    Estratégia: a linha inteira fica em uma única entrada de diálogo ASS,
    com as tags de cor inline — muito mais eficiente que uma entrada por palavra.
    """
    partes: list[str] = []
    for palavra in leg.palavras:
        texto_safe  = _escapar(palavra.texto)
        if not texto_safe:
            continue
        cor_html    = config.CORES_HTML.get(palavra.classe, "#666666")
        cor_fundo   = _html_para_ass_cor(cor_html)
        cor_texto   = _cor_texto_ass(palavra.classe)

        # tag override ASS:
        # \1c  = cor primária (texto)
        # \3c  = cor de borda (usamos como "fundo" com borda larga)
        # \bord = largura da borda — aumentamos para simular box
        # \shad0 = sem sombra
        partes.append(
            f"{{\\1c{cor_texto}\\3c{cor_fundo}\\bord{config.BOX_BORDER}\\shad0}}"
            f"{texto_safe} "
        )

    if not partes:
        _adicionar_linha_simples(linhas, leg, y, config)
        return

    texto_combinado = "".join(partes).rstrip()
    texto_ass = (
        f"{{\\an2\\pos({config.LARGURA_TELA // 2},{y})"
        f"\\fs{config.TAMANHO_FONTE_TAG}}}"
        + texto_combinado
    )

    linhas.append(_LINHA_DIALOGO.format(
        inicio=_ms_para_ass(leg.inicio_ms),
        fim   =_ms_para_ass(leg.fim_ms),
        texto =texto_ass,
    ))


# ── Queima de legendas ASS ────────────────────────────────────────────────────

def queimar_legendas_ass(
    video_entrada: Path | str,
    ass_path:      Path | str,
    saida:         Path | str,
) -> Path:
    """
    Queima o arquivo ASS no vídeo usando um único filtro `ass=`.
    Um único passe para todos os idiomas — substitui todos os drawtexts.
    """
    saida = Path(saida)
    # O caminho do .ass precisa de barras normais no FFmpeg (mesmo no Windows/Colab)
    ass_str = str(Path(ass_path).resolve()).replace("\\", "/")

    _run(
        ["ffmpeg", "-y",
         "-i", str(video_entrada),
         "-vf", f"ass={ass_str}",
         "-c:a", "copy",
         "-c:v", "libx264",
         "-preset", "medium",
         "-crf", "23",
         str(saida)],
        "queimar_ass",
    )
    logger.info("queimar_legendas_ass: %s → %s", Path(video_entrada).name, saida.name)
    return saida

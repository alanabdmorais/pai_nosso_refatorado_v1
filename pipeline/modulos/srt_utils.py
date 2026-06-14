# -*- coding: utf-8 -*-
"""
srt_utils.py — Utilitários para arquivos SRT.

Funções:
    ler_srt(caminho)                          → List[Legenda]
    salvar_srt(legendas, caminho)
    eliminar_gaps(legendas)                   → List[Legenda]   ← crítico para sync
    resegmentar_por_frase(legendas)           → List[Legenda]   ← re-segmenta YouTube
    ajustar_timestamps(legendas, delta_ms)
    validar_srt(legendas)                     → bool
    texto_corrido(legendas)                   → str
    extrair_texto_unico(legendas)             → str             (remove duplicatas do YouTube)
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from models import Legenda, str_para_ms

logger = logging.getLogger(__name__)


# ── Leitura ───────────────────────────────────────────────────────────────────

def ler_srt(caminho: Path | str) -> list[Legenda]:
    """
    Lê um arquivo SRT e retorna lista de Legenda.

    Suporta:
    - encoding utf-8 e utf-8-sig (com BOM)
    - timestamps com vírgula (00:00:01,000) e ponto (00:00:01.000)
    - múltiplas linhas de texto por bloco
    - artefatos do YouTube entre colchetes [Music], [Applause]
    """
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(f"SRT não encontrado: {caminho}")

    conteudo = caminho.read_text(encoding="utf-8-sig")
    blocos   = re.split(r"\n\s*\n", conteudo.strip())
    legendas: list[Legenda] = []

    for bloco in blocos:
        linhas = [l.strip() for l in bloco.strip().splitlines() if l.strip()]
        # linha de timestamp
        ts_linha = next((l for l in linhas if "-->" in l), None)
        if not ts_linha:
            continue
        partes = ts_linha.split("-->")
        if len(partes) != 2:
            continue
        inicio_ms = str_para_ms(partes[0].strip())
        fim_ms    = str_para_ms(partes[1].strip())

        # linhas de texto (exclui número do bloco e timestamp)
        textos = [
            l for l in linhas
            if "-->" not in l and not l.isdigit() and l != " "
        ]
        texto = " ".join(textos).strip()
        # remove artefatos do YouTube [Music], [Applause], etc.
        texto = re.sub(r"\[.*?\]", "", texto).strip()

        if not texto:
            continue

        legendas.append(Legenda(
            id        = len(legendas) + 1,
            inicio_ms = inicio_ms,
            fim_ms    = fim_ms,
            texto     = texto,
        ))

    logger.debug("ler_srt('%s'): %d legendas", caminho.name, len(legendas))
    return legendas


# ── Escrita ───────────────────────────────────────────────────────────────────

def salvar_srt(legendas: list[Legenda], caminho: Path | str) -> None:
    """Salva lista de Legenda como arquivo SRT (utf-8 sem BOM)."""
    caminho = Path(caminho)
    linhas: list[str] = []
    for i, leg in enumerate(legendas, 1):
        linhas.append(str(i))
        linhas.append(f"{leg.inicio_str} --> {leg.fim_str}")
        linhas.append(leg.texto)
        linhas.append("")
    caminho.write_text("\n".join(linhas), encoding="utf-8")
    logger.debug("salvar_srt('%s'): %d legendas", caminho.name, len(legendas))


# ── Ajuste de timestamps ──────────────────────────────────────────────────────

def eliminar_gaps(legendas: list[Legenda]) -> list[Legenda]:
    """
    Elimina os gaps entre legendas consecutivas.

    Para cada par (i, i+1): fim[i] = início[i+1] - 1ms.
    Isso garante que as legendas ASS/drawtext ficam visíveis sem buracos.
    O último bloco não é alterado.
    """
    for i in range(len(legendas) - 1):
        novo_fim = legendas[i + 1].inicio_ms - 1
        if novo_fim > legendas[i].inicio_ms:
            legendas[i].fim_ms = novo_fim
    logger.debug("eliminar_gaps: %d legendas processadas", len(legendas))
    return legendas


def ajustar_timestamps(legendas: list[Legenda], delta_ms: int) -> list[Legenda]:
    """
    Desloca todos os timestamps por delta_ms (pode ser negativo).
    Garante que inicio_ms e fim_ms nunca ficam abaixo de 0.
    """
    for leg in legendas:
        leg.inicio_ms = max(0, leg.inicio_ms + delta_ms)
        leg.fim_ms    = max(0, leg.fim_ms    + delta_ms)
    return legendas


def sincronizar_timestamps(
    legendas_alvo: list[Legenda],
    legendas_mestre: list[Legenda],
) -> list[Legenda]:
    """
    Copia os timestamps de legendas_mestre para legendas_alvo,
    alinhando por índice. Usado para garantir que EN/ES/FR usam
    exatamente os mesmos timestamps que o PT corrigido.
    """
    for i, (alvo, mestre) in enumerate(zip(legendas_alvo, legendas_mestre)):
        alvo.inicio_ms = mestre.inicio_ms
        alvo.fim_ms    = mestre.fim_ms
    logger.debug("sincronizar_timestamps: %d pares alinhados", min(len(legendas_alvo), len(legendas_mestre)))
    return legendas_alvo


# ── Validação ─────────────────────────────────────────────────────────────────

def validar_srt(legendas: list[Legenda]) -> bool:
    """
    Valida consistência básica de uma lista de legendas.
    Retorna True se tudo OK, False se houver problemas (e loga os erros).
    """
    ok = True
    for leg in legendas:
        if leg.inicio_ms >= leg.fim_ms:
            logger.warning("Legenda %d: inicio (%d) >= fim (%d)", leg.id, leg.inicio_ms, leg.fim_ms)
            ok = False
        if not leg.texto:
            logger.warning("Legenda %d: texto vazio", leg.id)
            ok = False
    # sobreposições
    for i in range(len(legendas) - 1):
        if legendas[i].fim_ms > legendas[i + 1].inicio_ms:
            logger.warning(
                "Sobreposição entre legendas %d e %d",
                legendas[i].id, legendas[i + 1].id,
            )
    return ok


# ── Extração de texto ─────────────────────────────────────────────────────────

def resegmentar_por_frase(legendas: list[Legenda]) -> list[Legenda]:
    """
    Re-segmenta legendas do YouTube em frases completas usando a pontuação.

    O YouTube gera legendas com frases cortadas no meio, tipo:
        [01] Pai nosso que estais no céu, santificado seja o
        [02] vosso nome, venha a nós o vosso reino...

    Esta função junta todo o texto, divide por pontuação de fim de frase
    (vírgula, ponto, ponto-e-vírgula) e redistribui os timestamps
    proporcionalmente ao número de caracteres de cada frase.

    Retorna lista de Legenda com frases completas e timestamps interpolados.
    """
    if not legendas:
        return legendas

    # 1. Juntar texto corrido e timestamps totais
    inicio_total = legendas[0].inicio_ms
    fim_total    = legendas[-1].fim_ms
    duracao_total = fim_total - inicio_total
    texto_total  = " ".join(leg.texto for leg in legendas)

    # 2. Dividir em frases por pontuação final
    # Mantém o separador junto com a frase anterior
    partes = re.split(r'(?<=[,;\.!?])\s+', texto_total.strip())
    frases = [p.strip() for p in partes if p.strip()]

    if len(frases) <= 1:
        # Não conseguiu segmentar — retorna original
        logger.warning("resegmentar_por_frase: não encontrou pontuação suficiente, retornando original")
        return legendas

    # 3. Redistribuir timestamps proporcionalmente ao nº de caracteres
    total_chars = sum(len(f) for f in frases)
    novas: list[Legenda] = []
    cursor_ms = inicio_total

    for i, frase in enumerate(frases):
        proporcao  = len(frase) / total_chars if total_chars > 0 else 1 / len(frases)
        duracao_ms = round(duracao_total * proporcao)
        inicio_ms  = cursor_ms
        fim_ms     = cursor_ms + duracao_ms

        # Último segmento vai exatamente até o fim
        if i == len(frases) - 1:
            fim_ms = fim_total

        novas.append(Legenda(
            id        = i + 1,
            inicio_ms = inicio_ms,
            fim_ms    = fim_ms,
            texto     = frase,
        ))
        cursor_ms = fim_ms

    logger.info(
        "resegmentar_por_frase: %d → %d segmentos  [%.1fs – %.1fs]",
        len(legendas), len(novas),
        inicio_total / 1000, fim_total / 1000,
    )
    return novas


def texto_corrido(legendas: list[Legenda]) -> str:
    """Junta todos os textos em uma única string separada por espaço."""
    return " ".join(leg.texto for leg in legendas)


def extrair_texto_unico(legendas: list[Legenda]) -> str:
    """
    Remove frases duplicadas (artefato comum do YouTube auto-captions).
    Tenta detectar padrões "frase frase" onde a frase se repete.
    Retorna o texto corrido sem duplicatas.
    """
    frases_unicas: list[str] = []
    visto: set[str] = set()

    for leg in legendas:
        # filtra legendas muito curtas (< 50ms = artefato)
        if leg.duracao_ms < 50:
            continue
        frase = _extrair_prefixo(leg.texto)
        if frase and frase not in visto:
            frases_unicas.append(frase)
            visto.add(frase)

    return " ".join(frases_unicas)


def _extrair_prefixo(texto: str) -> str:
    """
    Detecta o padrão "A A" onde A é a primeira metade do texto.
    Retorna A se encontrar repetição, senão retorna o texto original.
    """
    tokens = texto.split()
    n = len(tokens)
    for i in range(1, n // 2 + 1):
        prefixo = " ".join(tokens[:i])
        seguinte = " ".join(tokens[i: i * 2])
        if prefixo == seguinte:
            return prefixo
    return texto

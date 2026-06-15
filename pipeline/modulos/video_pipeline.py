# -*- coding: utf-8 -*-
"""
video_pipeline.py — Orquestrador principal do pipeline.

FASE 5 — Estratégia intermediária de classificação:
  5A: Groq classifica → JSON bruto salvo local + Drive backup
       → exporta pacote de revisão (JSONs + CSV + prompt)
       → PAUSA e instrui o usuário
  5B: Usuário coloca JSONs revisados no Drive
       → Pipeline recarrega e continua nas fases 6-8

Retomada de qualquer fase:
    pipeline.run(from_phase="nome_da_fase")
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from checkpoint import Checkpoint
from classification import Classifier
from config import PipelineConfig
from constants import FASES_PIPELINE
from drive_utils import DriveClient
from ffmpeg_utils import (
    FFmpegError,
    adicionar_audio,
    adicionar_credito_e_logo,
    adicionar_trilha_fundo,
    concatenar_videos,
    cortar_video,
    gerar_ass,
    obter_duracao,
    queimar_legendas_ass,
)
from groq_client import GroqClient
from models import Clipe, Legenda
from srt_utils import (
    eliminar_gaps,
    extrair_texto_unico,
    ler_srt,
    resegmentar_por_frase,
    salvar_srt,
    sincronizar_timestamps,
)

logger = logging.getLogger(__name__)

_SEP = "=" * 65


# ─── EXCEÇÕES DO PIPELINE ─────────────────────────────────────────────────────

class PipelineError(Exception):
    """Erro geral do pipeline."""
    pass


class ClassificacaoPendenteError(PipelineError):
    """
    Sinal de pausa intencional: classificações precisam de revisão manual.
    Não é um erro — é parte do fluxo intermediário.
    
    Esta exceção é lançada quando novos JSONs foram gerados e precisam
    ser revisados pelo usuário antes de continuar.
    """
    pass


# ─── CLASSE PRINCIPAL ─────────────────────────────────────────────────────────

class VideoPipeline:
    """Orquestrador do pipeline de vídeo com legendas morfológicas multilíngues."""

    def __init__(self, config: PipelineConfig, groq: GroqClient) -> None:
        config.validate()
        self._cfg   = config
        self._groq  = groq
        self._drive = DriveClient.get()
        self._cp    = Checkpoint()
        self._clf   = Classifier(config, groq)
        # Estado em memória das legendas (para retomada na 5B sem recarregar tudo)
        self.legendas_idiomas: dict[str, list[Legenda]] = {}

    # ── Ponto de entrada ──────────────────────────────────────────────────────

    def run(self, from_phase: Optional[str] = None) -> Optional[Path]:
        """
        Executa o pipeline completo com checkpoint.
        Na fase 5, pode pausar e retornar None — nesse caso rode:
            pipeline.run(from_phase='clipes_cortados')
        após colocar os JSONs revisados no Drive.
        """
        if from_phase:
            logger.info("🔄 Reiniciando a partir de: %s", from_phase)
            self._cp.reiniciar_de(from_phase)

        logger.info(_SEP)
        logger.info("▶  PIPELINE — %s", self._cfg.NOME_ORACAO.upper())
        logger.info(_SEP)
        logger.info(self._cp.resumo())

        legendas_pt: list[Legenda] = []
        clipes:      list[Clipe]   = []

        # Fase 1
        if not self._cp.fase_concluida("audio_gerado"):
            self.fase1_gerar_audio()
        else:
            logger.info("⏭️  Fase 1 (áudio) já concluída")

        # Fase 2 - REMOVIDA (Whisper não é mais usado)
        # O pipeline agora usa YouTube como fonte principal
        logger.info("⏭️  Fase 2 pulada (Whisper desativado - usando YouTube como fonte)")
        if not self._cp.fase_concluida("srt_pt_bruto"):
            srt_youtube = Path(self._cfg.nome_srt('pt'))
            if srt_youtube.exists():
                self._cp.salvar("srt_pt_bruto", {"fonte": "youtube", "segmentos": len(ler_srt(srt_youtube))})
            else:
                self._cp.salvar("srt_pt_bruto", {"fonte": "nenhum", "observacao": "YouTube não disponível"})

        # Fase 3 - usa YouTube como mestre
        if not self._cp.fase_concluida("srt_pt_corrigido"):
            legendas_pt = self.fase3_corrigir_pt()
        else:
            logger.info("⏭️  Fase 3 (correção PT) já concluída")
            legendas_pt = ler_srt(self._cfg.NOME_SRT_PT)

        # Fase 4
        if not self._cp.fase_concluida("srt_traduzidos"):
            self.legendas_idiomas = self.fase4_traduzir(legendas_pt)
        else:
            logger.info("⏭️  Fase 4 (traduções) já concluída")
            self.legendas_idiomas = self._carregar_todos_srts(legendas_pt)

        # Fase 5A — Groq classifica (pode pausar aqui)
        # Se VIDEO_SIMPLES_SEM_MORFOLOGIA=True: pula classificação, legenda toda na cor do idioma
        if self._cfg.VIDEO_SIMPLES_SEM_MORFOLOGIA:
            logger.info("🎨 MODO SIMPLES: pulando classificação morfológica (cores por idioma)")
            for lang in self.legendas_idiomas:
                for leg in self.legendas_idiomas[lang]:
                    leg.palavras = []
            self._cp.salvar("classificacoes_feitas", {"modo": "simples_sem_morfologia"})
        elif not self._cp.fase_concluida("classificacoes_feitas"):
            try:
                self.legendas_idiomas = self.fase5a_classificar_groq(self.legendas_idiomas)
            except ClassificacaoPendenteError:
                # Pausa intencional — usuário precisa revisar
                return None
        else:
            logger.info("⏭️  Fase 5 (classificação) já concluída")
            self.legendas_idiomas = self._carregar_classificacoes(self.legendas_idiomas)

        # Fase 6
        if not self._cp.fase_concluida("clipes_cortados"):
            clipes = self.fase6_baixar_clipes(legendas_pt)
        else:
            logger.info("⏭️  Fase 6 (clipes) já concluída")
            clipes = self._clipes_do_checkpoint()

        # Fase 7
        if not self._cp.fase_concluida("video_base_criado"):
            self.fase7_criar_video_base(clipes)
        else:
            logger.info("⏭️  Fase 7 (vídeo base) já concluída")

        # Fase 8
        if not self._cp.fase_concluida("legendas_queimadas"):
            video_final = self.fase8_queimar_legendas(self.legendas_idiomas)
        else:
            logger.info("⏭️  Fase 8 (legendas) já concluída")
            video_final = Path(self._cfg.NOME_VIDEO_FINAL)

        logger.info(_SEP)
        logger.info("🎉 PIPELINE CONCLUÍDO: %s", video_final)
        logger.info(_SEP)
        return video_final

    # ── Fase 1 ────────────────────────────────────────────────────────────────

    def fase1_gerar_audio(self) -> Path:
        """Gera áudio com Edge TTS e salva no Drive."""
        import edge_tts
        import threading

        logger.info("── Fase 1: Gerando áudio com Edge TTS")
        audio_path = Path(self._cfg.NOME_AUDIO)

        async def _gerar():
            for tentativa in range(1, 4):
                try:
                    comm = edge_tts.Communicate(self._cfg.TEXTO_ORACAO, self._cfg.VOZ_EDGE)
                    await comm.save(str(audio_path))
                    return
                except Exception as exc:
                    logger.warning("Edge TTS tentativa %d/3: %s", tentativa, exc)
                    await asyncio.sleep(2)
            raise PipelineError("Edge TTS falhou após 3 tentativas")

        # Executar em thread separada para evitar conflito de event loop
        def run_in_thread():
            asyncio.run(_gerar())
        
        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()

        logger.info("✅ Áudio: %s (%.2f MB)", audio_path.name, audio_path.stat().st_size / 1_048_576)
        self._drive.upload(audio_path, self._cfg.pasta_assets_audio, "audio/wav")
        self._cp.salvar("audio_gerado", {"arquivo": str(audio_path)})
        return audio_path

    # ── Atalho: vídeo base ANTES de existirem legendas do YouTube ─────────────

    def gerar_video_base(self) -> Path:
        """
        Gera o vídeo base (clipes + crédito/logo + narração + trilha) sem
        depender das legendas do YouTube (Fases 3/4/5/8) — útil porque o
        YouTube só gera as legendas DEPOIS que esse vídeo base é publicado.

        Executa, na ordem:
          - Fase 1 (áudio), se ainda não feita
          - Fase 6 (clipes), usando a duração do áudio em vez de legendas_pt
          - Fase 7 (vídeo base), com download oferecido ao final

        Pode ser chamado a qualquer momento; depois de publicar o vídeo e
        baixar as legendas do YouTube, rode pipeline.run() normalmente —
        as fases 1, 6 e 7 serão puladas pelo checkpoint.
        """
        logger.info(_SEP)
        logger.info("▶  GERAR VÍDEO BASE (sem legendas do YouTube) — %s", self._cfg.NOME_ORACAO.upper())
        logger.info(_SEP)

        if not self._cp.fase_concluida("audio_gerado"):
            self.fase1_gerar_audio()
        else:
            logger.info("⏭️  Fase 1 (áudio) já concluída")

        if not self._cp.fase_concluida("clipes_cortados"):
            clipes = self.fase6_baixar_clipes()
        else:
            logger.info("⏭️  Fase 6 (clipes) já concluída")
            clipes = self._clipes_do_checkpoint()

        if not self._cp.fase_concluida("video_base_criado"):
            video_base = self.fase7_criar_video_base(clipes)
        else:
            logger.info("⏭️  Fase 7 (vídeo base) já concluída")
            video_base = Path(self._cfg.NOME_VIDEO_BASE)

        logger.info(_SEP)
        logger.info("🎉 VÍDEO BASE PRONTO: %s", video_base)
        logger.info("   Publique este vídeo no YouTube. Depois que o YouTube")
        logger.info("   gerar as legendas automáticas, baixe-as e rode pipeline.run()")
        logger.info("   normalmente — as fases já feitas serão puladas.")
        logger.info(_SEP)
        return video_base

    # ── Fase 2 (MANTIDA APENAS PARA REFERÊNCIA, NÃO É MAIS USADA) ─────────────

    def fase2_transcrever_whisper(self) -> Path:
        """Transcreve o áudio com Whisper (NÃO É MAIS USADO - mantido apenas para referência)."""
        import whisper

        logger.info("── Fase 2: Transcrevendo com Whisper (NÃO USADO - YouTube é preferido)")
        audio_path = Path(self._cfg.NOME_AUDIO)
        if not audio_path.exists():
            self._drive.download(self._cfg.pasta_assets_audio, self._cfg.NOME_AUDIO, audio_path)

        model     = whisper.load_model("base")
        resultado = model.transcribe(str(audio_path), language="pt", word_timestamps=True)

        legendas: list[Legenda] = []
        for seg in resultado["segments"]:
            legendas.append(Legenda(
                id        = len(legendas) + 1,
                inicio_ms = int(seg["start"] * 1000),
                fim_ms    = int(seg["end"]   * 1000),
                texto     = seg["text"].strip(),
            ))

        srt_edge = Path(self._cfg.NOME_SRT_PT_EDGE)
        salvar_srt(legendas, srt_edge)
        logger.info("✅ SRT bruto (Whisper): %s (%d segmentos)", srt_edge.name, len(legendas))
        return srt_edge

    # ── Fase 3 - usa YouTube como MESTRE (Whisper apenas como fallback) ───────

    def fase3_corrigir_pt(self) -> list[Legenda]:
        """
        Produz o SRT PT definitivo.

        Estrategia (Whisper como MESTRE de timestamps):
        1. Whisper define inicio_ms/fim_ms de cada legenda (segmentação por pausas naturais)
        2. YouTube fornece o texto PT correto (sem erros de transcrição)
        3. Groq faz apenas limpeza leve de artefatos no texto do YouTube
        4. Texto limpo é aplicado nos timestamps do Whisper

        Fallback: se YouTube não disponível, usa só o texto do Whisper
        """
        logger.info("── Fase 3: SRT PT definitivo (Whisper timestamps + YouTube texto)")

        # ── Passo 1: Whisper → timestamps mestre ───────────────────────────
        srt_whisper = Path(self._cfg.NOME_SRT_PT_EDGE)
        if not srt_whisper.exists():
            logger.info("   🎙️ Gerando transcrição Whisper...")
            srt_whisper = self.fase2_transcrever_whisper()
        else:
            logger.info("   🎙️ Whisper já gerado: %s", srt_whisper.name)

        legendas_timestamps = ler_srt(srt_whisper)
        logger.info("   📊 Whisper: %d segmentos (timestamps mestre)", len(legendas_timestamps))

        # ── Passo 2: YouTube → texto PT ────────────────────────────────────
        srt_youtube = Path(self._cfg.nome_srt('pt'))
        if srt_youtube.exists():
            logger.info("   📺 YouTube PT encontrado — extraindo texto")
            texto_youtube = " ".join(leg.texto for leg in ler_srt(srt_youtube))

            # ── Passo 3: Groq → limpeza leve de artefatos ──────────────────
            logger.info("   🤖 Groq limpando artefatos do texto YouTube...")
            texto_limpo = self._groq.limpar_artefatos(texto_youtube)
            logger.info("   ✅ Texto limpo: %s...", texto_limpo[:60])

            # ── Passo 4: Aplicar texto nos timestamps do Whisper ───────────
            legendas = self._aplicar_texto_nos_timestamps(legendas_timestamps, texto_limpo)
            fonte = "whisper_timestamps+youtube_texto"
        else:
            logger.warning("   ⚠️  YouTube PT não encontrado — usando texto do Whisper")
            legendas = legendas_timestamps
            fonte = "whisper_completo"

        srt_pt = Path(self._cfg.NOME_SRT_PT)
        salvar_srt(legendas, srt_pt)
        self._drive.upload(srt_pt, self._cfg.pasta_assets_legendas, "text/plain")
        logger.info("✅ SRT PT salvo: %s (%d legendas) [%s]", srt_pt.name, len(legendas), fonte)
        self._cp.salvar("srt_pt_corrigido", {"legendas": len(legendas), "fonte": fonte})
        return legendas

    def _aplicar_texto_nos_timestamps(
        self,
        legendas_timestamps: list[Legenda],
        texto_completo: str,
    ) -> list[Legenda]:
        """
        Aplica o texto limpo (YouTube) nos timestamps do Whisper.
        Mantém o número de segmentos do Whisper.
        Se o número de frases divergir, redistribui proporcionalmente.
        """
        import re

        # Divide por pontuação de fim de frase
        frases = [f.strip() for f in re.split(r"(?<=[.!?;,])\s+", texto_completo.strip()) if f.strip()]

        n_whisper = len(legendas_timestamps)
        n_frases  = len(frases)

        if n_frases == n_whisper:
            # Caso ideal: mesmo número → substitui texto diretamente
            for leg, frase in zip(legendas_timestamps, frases):
                leg.texto = frase
            logger.info("   ✅ Texto aplicado diretamente (%d segmentos)", n_whisper)
        else:
            logger.warning(
                "   ⚠️  Whisper=%d segmentos, YouTube=%d frases — redistribuindo",
                n_whisper, n_frases,
            )
            legendas_timestamps = self._redistribuir_texto(legendas_timestamps, frases)

        return legendas_timestamps

    def _redistribuir_texto(
        self,
        legendas_timestamps: list[Legenda],
        frases: list[str],
    ) -> list[Legenda]:
        """
        Redistribui N frases em M segmentos de forma proporcional à duração.
        Usado quando YouTube e Whisper têm números diferentes de segmentos.
        """
        texto_total = " ".join(frases)
        total_chars = max(len(texto_total), 1)
        duracao_total = legendas_timestamps[-1].fim_ms - legendas_timestamps[0].inicio_ms
        inicio_base   = legendas_timestamps[0].inicio_ms

        # Montar novos segmentos mantendo timestamps do Whisper
        # (preferência: um segmento Whisper = uma frase, excedentes concatenam)
        n = len(legendas_timestamps)
        if len(frases) >= n:
            # Agrupa frases nos slots do Whisper
            grupos: list[list[str]] = [[] for _ in range(n)]
            for i, frase in enumerate(frases):
                grupos[min(i, n - 1)].append(frase)
            for leg, grupo in zip(legendas_timestamps, grupos):
                leg.texto = " ".join(grupo)
        else:
            # Menos frases que segmentos: distribui proporcionalmente por caractere
            cursor = 0
            for i, leg in enumerate(legendas_timestamps):
                proporcao = (leg.fim_ms - leg.inicio_ms) / max(duracao_total, 1)
                n_chars   = max(int(total_chars * proporcao), 1)
                leg.texto = texto_total[cursor: cursor + n_chars].strip()
                cursor   += n_chars
            # Garante que o último segmento pega o restante
            legendas_timestamps[-1].texto = texto_total[cursor:].strip() or legendas_timestamps[-1].texto

        logger.info("   ✅ Redistribuído: %d segmentos", n)
        return legendas_timestamps

    # ── Fase 4 ────────────────────────────────────────────────────────────────

    def fase4_traduzir(self, legendas_pt: list[Legenda]) -> dict[str, list[Legenda]]:
        """
        Carrega legendas EN/ES/FR direto do YouTube (sem Groq).
        Sincroniza timestamps com PT (mestre).

        Se o YouTube não tiver o idioma: usa PT como fallback (sem tradução via Groq).
        Artefatos são removidos localmente com regex — sem chamada de API.
        """
        import re
        logger.info("── Fase 4: Carregando EN/ES/FR do YouTube (sem Groq)")
        legendas_idiomas: dict[str, list[Legenda]] = {"pt": legendas_pt}

        # Regex para limpeza local de artefatos
        _ARTEFATOS = re.compile(
            r"\[.*?\]"                   # [Música], [Aplausos], etc.
            r"|[A-Z]{1,2}\.?"        # M., M, METRO soltos
            r"|METRO",
            re.IGNORECASE,
        )

        for lang in [l for l in self._cfg.IDIOMAS if l != "pt"]:
            logger.info("   📺 %s — carregando do YouTube...", lang.upper())
            srt_yt = Path(self._cfg.nome_srt(lang))

            if srt_yt.exists():
                legendas_raw = ler_srt(srt_yt)

                # Limpeza local de artefatos (regex, sem API)
                for leg in legendas_raw:
                    leg.texto = _ARTEFATOS.sub("", leg.texto).strip()
                    leg.texto = re.sub(r"\s{2,}", " ", leg.texto).strip()

                # Sincronizar timestamps com PT (Whisper é o mestre)
                legendas_lang = sincronizar_timestamps(legendas_raw, legendas_pt)
                fonte = "youtube_direto"
            else:
                logger.warning(
                    "   ⚠️  YouTube não disponível para %s — usando PT como fallback",
                    lang.upper(),
                )
                legendas_lang = [
                    Legenda(id=leg.id, inicio_ms=leg.inicio_ms,
                            fim_ms=leg.fim_ms, texto=leg.texto)
                    for leg in legendas_pt
                ]
                fonte = "fallback_pt"

            legendas_idiomas[lang] = legendas_lang
            srt_out = Path(self._cfg.nome_srt(lang))
            salvar_srt(legendas_lang, srt_out)
            self._drive.upload(srt_out, self._cfg.pasta_assets_legendas, "text/plain")
            logger.info("   ✅ %s: %d legendas [%s]", lang.upper(), len(legendas_lang), fonte)

        self._cp.salvar("srt_traduzidos", {"idiomas": list(legendas_idiomas.keys())})
        return legendas_idiomas

    # ── Fase 5A — Groq classifica ─────────────────────────────────────────────

    def fase5a_classificar_groq(
        self, legendas_idiomas: dict[str, list[Legenda]]
    ) -> dict[str, list[Legenda]]:
        """
        Classifica morfologicamente via Groq (ou carrega cache existente).
        Se algum idioma for gerado pelo Groq, exporta o pacote de revisão
        e pausa o pipeline com instruções claras.

        Lança ClassificacaoPendenteError quando há JSONs novos para revisar.
        Se TODOS os idiomas já têm JSONs corrigidos no Drive, segue direto.
        """
        logger.info("── Fase 5A: Classificação morfológica")
        self._clf.imprimir_status()

        # Verifica se todos já estão corrigidos no Drive
        todos_corrigidos = all(
            self._clf.existe_corrigido(lang) for lang in self._cfg.IDIOMAS
        )
        if todos_corrigidos:
            logger.info("✅ Todos os idiomas já têm JSONs corrigidos no Drive — carregando")
            for lang, legendas in legendas_idiomas.items():
                self._clf.carregar_para_legendas(legendas, lang)
            self._cp.salvar("classificacoes_feitas", {"fonte": "drive_corrigido"})
            return legendas_idiomas

        # Classifica os que ainda não têm JSON (bruto ou corrigido)
        novos: list[str] = []
        for lang, legendas in legendas_idiomas.items():
            if self._clf.existe_corrigido(lang):
                logger.info("   ⏭️  %s: já corrigido no Drive — pulando", lang.upper())
                self._clf.carregar_para_legendas(legendas, lang)
            elif self._clf.existe_bruto(lang):
                logger.info("   📁 %s: carregando JSON bruto existente", lang.upper())
                self._clf.carregar_para_legendas(legendas, lang)
            else:
                logger.info("   🤖 %s: classificando via Groq...", lang.upper())
                self._clf.classificar_idioma(legendas, lang, forcar=True)
                novos.append(lang)

        # Exporta pacote de revisão se gerou novos JSONs
        if novos:
            logger.info("📦 Novos JSONs gerados (%s) → exportando pacote de revisão", ", ".join(novos))
            pacote = self._clf.exportar_pacote_revisao(legendas_idiomas)
            self._imprimir_instrucoes_revisao(pacote, novos)
            raise ClassificacaoPendenteError(
                f"Classificações geradas para: {novos}. "
                "Revise os JSONs e execute fase5b_recarregar()."
            )

        # Chegou aqui = todos os JSONs brutos existem, mas nenhum novo foi gerado
        # (situação: run() chamado de novo após Groq mas antes da revisão)
        self._imprimir_instrucoes_revisao(None, [])
        raise ClassificacaoPendenteError("JSONs brutos aguardam revisão manual.")

    def fase5b_recarregar(self) -> dict[str, list[Legenda]]:
        """
        Recarrega as classificações após revisão manual no Drive.
        Chame esta função depois de colocar os JSONs corrigidos no Drive.

        Retorna legendas_idiomas com palavras classificadas.
        """
        logger.info("── Fase 5B: Recarregando classificações corrigidas")

        if not self.legendas_idiomas:
            # Pipeline foi reiniciado — recarrega SRTs
            legendas_pt = ler_srt(self._cfg.NOME_SRT_PT)
            self.legendas_idiomas = self._carregar_todos_srts(legendas_pt)

        self._clf.invalidar_cache()
        self._clf.imprimir_status()

        pendentes = [
            lang for lang in self._cfg.IDIOMAS
            if not self._clf.existe_corrigido(lang)
        ]
        if pendentes:
            logger.warning(
                "⚠️  Os seguintes idiomas ainda não têm JSON corrigido no Drive: %s",
                ", ".join(pendentes),
            )
            logger.warning(
                "   Usando JSONs brutos para eles. Corrija e rode fase5b_recarregar() de novo se quiser."
            )

        for lang, legendas in self.legendas_idiomas.items():
            self._clf.carregar_para_legendas(legendas, lang)
            logger.info("   ✅ %s carregado", lang.upper())

        self._cp.salvar("classificacoes_feitas", {"fonte": "drive_corrigido"})
        logger.info("✅ Fase 5B concluída — execute as fases 6, 7 e 8 (ou pipeline.continuar())")
        return self.legendas_idiomas

    def continuar(self) -> Path:
        """
        Retoma o pipeline a partir da fase 6 (clipes), usando legendas_idiomas
        já carregadas em memória pela fase5b_recarregar().
        Atalho para não precisar chamar run(from_phase=...) manualmente.
        """
        if not self.legendas_idiomas:
            raise PipelineError(
                "legendas_idiomas vazio. Execute fase5b_recarregar() antes de continuar()."
            )
        if not self._cp.fase_concluida("classificacoes_feitas"):
            raise PipelineError(
                "Fase 5 não marcada como concluída. Execute fase5b_recarregar() primeiro."
            )

        legendas_pt = self.legendas_idiomas.get("pt") or ler_srt(self._cfg.NOME_SRT_PT)

        # Fase 6
        if not self._cp.fase_concluida("clipes_cortados"):
            clipes = self.fase6_baixar_clipes(legendas_pt)
        else:
            logger.info("⏭️  Fase 6 já concluída")
            clipes = self._clipes_do_checkpoint()

        # Fase 7
        if not self._cp.fase_concluida("video_base_criado"):
            self.fase7_criar_video_base(clipes)
        else:
            logger.info("⏭️  Fase 7 já concluída")

        # Fase 8
        if not self._cp.fase_concluida("legendas_queimadas"):
            video_final = self.fase8_queimar_legendas(self.legendas_idiomas)
        else:
            logger.info("⏭️  Fase 8 já concluída")
            video_final = Path(self._cfg.NOME_VIDEO_FINAL)

        logger.info(_SEP)
        logger.info("🎉 CONCLUÍDO: %s", video_final)
        logger.info(_SEP)
        return video_final

    # ── Fase 6 ────────────────────────────────────────────────────────────────

    def fase6_baixar_clipes(self, legendas_pt: Optional[list[Legenda]] = None) -> list[Clipe]:
        """
        Baixa clipes da planilha Google Sheets e corta para DURACAO_CLIPE segundos.

        A duração total do vídeo é calculada a partir de `legendas_pt` (se
        fornecido) ou, na ausência delas (ex: vídeo base gerado antes das
        legendas do YouTube existirem), a partir da duração do áudio gerado
        na Fase 1.
        """
        logger.info("── Fase 6: Baixando e cortando clipes")

        if legendas_pt:
            duracao_total = max(leg.fim_seg for leg in legendas_pt)
        else:
            audio_path = Path(self._cfg.NOME_AUDIO)
            self._drive.download_se_ausente(self._cfg.pasta_assets_audio, self._cfg.NOME_AUDIO, audio_path)
            if not audio_path.exists():
                raise PipelineError(
                    "Não foi possível determinar a duração: nem legendas_pt "
                    "nem o áudio gerado estão disponíveis."
                )
            duracao_total = obter_duracao(audio_path)
            logger.info("   Duração obtida do áudio gerado (sem legendas_pt)")

        num_clipes    = max(1, int(duracao_total / self._cfg.DURACAO_CLIPE) + 1)
        logger.info("   Duração total: %.1fs → %d clipes necessários", duracao_total, num_clipes)

        url_csv = (
            f"https://docs.google.com/spreadsheets/d/"
            f"{self._cfg.ID_PLANILHA_DRIVE}/export?format=csv"
        )
        df = pd.read_csv(url_csv)
        if len(df) < num_clipes:
            raise PipelineError(f"Planilha tem {len(df)} clipes, precisamos de {num_clipes}")

        clipes = [
            Clipe(url=str(row["url"]), autor=str(row.get("Autor", "Pixabay")), indice=idx)
            for idx, (_, row) in enumerate(df.head(num_clipes).iterrows())
        ]

        Path("clipes_cortados").mkdir(exist_ok=True)
        Path("temp_raw").mkdir(exist_ok=True)

        processados: list[Clipe] = []
        with ThreadPoolExecutor(max_workers=self._cfg.FFMPEG_NUM_THREADS) as executor:
            futures = {executor.submit(self._processar_clipe, c): c for c in clipes}
            for future in as_completed(futures):
                clipe = futures[future]
                try:
                    result = future.result()
                    if result:
                        processados.append(result)
                        logger.info("   ✅ [%d/%d] %s", len(processados), num_clipes, clipe.autor)
                except Exception as exc:
                    logger.warning("   ❌ Clipe %d: %s", clipe.indice, exc)

        if not processados:
            raise PipelineError("Nenhum clipe processado com sucesso")

        # Backup dos clipes prontos na pasta de assets do Drive
        try:
            self._cfg.pasta_assets_clipes.mkdir(parents=True, exist_ok=True)
            for clipe in processados:
                self._drive.upload(Path(clipe.arquivo_pronto), self._cfg.pasta_assets_clipes, "video/mp4")
        except Exception as exc:
            logger.warning("   ⚠️  Backup de clipes no Drive falhou: %s", exc)

        self._cp.salvar("clipes_cortados", {
            "total": len(processados),
            "clipes": [{"indice": c.indice, "arquivo": c.arquivo_pronto, "autor": c.autor} for c in processados],
        })
        return processados

    def _processar_clipe(self, clipe: Clipe) -> Optional[Clipe]:
        raw   = Path(f"temp_raw/raw_{clipe.indice}.mp4")
        saida = Path(f"clipes_cortados/clipe_{clipe.indice:03d}.mp4")
        try:
            r = requests.get(clipe.url, headers={"User-Agent": "Mozilla/5.0"},
                             timeout=self._cfg.DOWNLOAD_TIMEOUT, stream=True)
            r.raise_for_status()
            with open(raw, "wb") as fh:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
        except Exception as exc:
            logger.debug("Download falhou clipe %d: %s", clipe.indice, exc)
            return None

        if not raw.exists() or raw.stat().st_size < 1000:
            return None
        try:
            cortar_video(raw, saida, self._cfg.DURACAO_CLIPE)
        except FFmpegError as exc:
            logger.debug("Corte falhou clipe %d: %s", clipe.indice, exc)
            raw.unlink(missing_ok=True)
            return None

        raw.unlink(missing_ok=True)
        if saida.exists() and saida.stat().st_size > 1000:
            clipe.arquivo_local = clipe.arquivo_pronto = str(saida)
            return clipe
        return None

    # ── Fase 7 ────────────────────────────────────────────────────────────────

    def fase7_criar_video_base(self, clipes: list[Clipe]) -> Path:
        """Adiciona crédito/logo, concatena, adiciona narração e trilha."""
        logger.info("── Fase 7: Criando vídeo base")

        logo_path = Path("logo_baixada.png")
        self._drive.download_se_ausente(self._cfg.pasta_assets_marca, self._cfg.NOME_ARQUIVO_LOGO, logo_path)
        if not logo_path.exists():
            logo_path = None  # type: ignore

        Path("clipes_prontos").mkdir(exist_ok=True)
        arquivos_prontos: list[Path] = []
        for clipe in sorted(clipes, key=lambda c: c.indice):
            entrada = Path(clipe.arquivo_pronto)
            saida   = Path(f"clipes_prontos/clipe_{clipe.indice:03d}.mp4")
            adicionar_credito_e_logo(entrada, saida, f"Pixabay / {clipe.autor}", logo_path, self._cfg.TAMANHO_LOGO)
            arquivos_prontos.append(saida)

        video_sem_audio = Path("video_sem_audio.mp4")
        concatenar_videos(arquivos_prontos, video_sem_audio)

        audio_path = Path(self._cfg.NOME_AUDIO)
        self._drive.download_se_ausente(self._cfg.pasta_assets_audio, self._cfg.NOME_AUDIO, audio_path)
        video_com_audio = Path("video_com_audio.mp4")
        adicionar_audio(video_sem_audio, audio_path, video_com_audio)
        video_sem_audio.unlink(missing_ok=True)

        musica_path = self._resolver_trilha_sonora()
        video_base = Path(self._cfg.NOME_VIDEO_BASE)
        if musica_path and musica_path.exists():
            adicionar_trilha_fundo(video_com_audio, musica_path, video_base, self._cfg.VOLUME_MUSICA)
            video_com_audio.unlink(missing_ok=True)
        else:
            video_com_audio.rename(video_base)
            logger.warning("Trilha não encontrada — vídeo base sem música de fundo")

        self._drive.upload(video_base, self._cfg.pasta_assets_videos, "video/mp4")
        logger.info("✅ Vídeo base: %s (%.2f MB)", video_base.name, video_base.stat().st_size / 1_048_576)
        self._cp.salvar("video_base_criado", {"arquivo": str(video_base)})
        self._oferecer_download(video_base, self._cfg.pasta_assets_videos)
        return video_base

    # ── Resolução da trilha sonora ───────────────────────────────────────────

    def _resolver_trilha_sonora(self) -> Optional[Path]:
        """
        Resolve o arquivo de trilha sonora em assets/trilha/.

        Prioridade:
          1. Arquivo com o nome configurado em cfg.NOME_ARQUIVO_MUSICA (se existir)
          2. Único arquivo de áudio (.mp3/.wav/.m4a/.ogg) presente em assets/trilha/
             — útil quando a trilha muda por oração e o nome não foi atualizado
               em config.py.

        Retorna o caminho local do arquivo baixado, ou None se não achar nada.
        """
        pasta_trilha = self._cfg.pasta_assets_trilha

        # 1. Tenta o nome configurado
        musica_path = Path(self._cfg.NOME_ARQUIVO_MUSICA)
        if self._drive.download_se_ausente(pasta_trilha, self._cfg.NOME_ARQUIVO_MUSICA, musica_path):
            if musica_path.exists():
                return musica_path

        # 2. Fallback: único arquivo de áudio na pasta trilha/ do Drive
        EXTENSOES_AUDIO = {".mp3", ".wav", ".m4a", ".ogg"}
        try:
            candidatos = [
                f for f in self._drive.listar_pasta(pasta_trilha)
                if Path(f["name"]).suffix.lower() in EXTENSOES_AUDIO
            ]
        except Exception as exc:
            logger.debug("Não foi possível listar %s: %s", pasta_trilha, exc)
            candidatos = []

        if len(candidatos) == 1:
            nome = candidatos[0]["name"]
            logger.info(
                "   🎵 Trilha '%s' não encontrada — usando '%s' (único arquivo em assets/trilha/)",
                self._cfg.NOME_ARQUIVO_MUSICA, nome,
            )
            destino = Path(nome)
            if self._drive.download(pasta_trilha, nome, destino):
                return destino
        elif len(candidatos) > 1:
            logger.warning(
                "   ⚠️  assets/trilha/ tem %d arquivos de áudio e nenhum corresponde a "
                "NOME_ARQUIVO_MUSICA ('%s') — ajuste config.py ou deixe só 1 arquivo na pasta.",
                len(candidatos), self._cfg.NOME_ARQUIVO_MUSICA,
            )

        return None

    # ── Download de assets ───────────────────────────────────────────────────

    @staticmethod
    def _oferecer_download(arquivo: Path, pasta_drive: Path) -> None:
        """
        Oferece o arquivo para download direto pelo navegador (Colab)
        e mostra o caminho onde ele foi salvo no Drive.
        """
        print(f"💾 Salvo no Drive: {pasta_drive / arquivo.name}")
        try:
            from google.colab import files
            print(f"⬇️  Iniciando download de {arquivo.name}...")
            files.download(str(arquivo))
        except Exception as exc:
            logger.debug("Download automático não disponível: %s", exc)
            print(f"   (download automático indisponível — baixe manualmente em: {pasta_drive / arquivo.name})")

    # ── Fase 8 ────────────────────────────────────────────────────────────────

    def fase8_queimar_legendas(self, legendas_idiomas: dict[str, list[Legenda]]) -> Path:
        """Gera o arquivo ASS e queima as legendas coloridas no vídeo final."""
        logger.info("── Fase 8: Queimando legendas ASS")

        video_base = Path(self._cfg.NOME_VIDEO_BASE)
        if not video_base.exists():
            raise PipelineError(f"Vídeo base não encontrado: {video_base}")

        legendas_pt = legendas_idiomas.get("pt", [])
        for lang, legendas in legendas_idiomas.items():
            if lang != "pt" and legendas_pt:
                sincronizar_timestamps(legendas, legendas_pt)

        ass_path = gerar_ass(
            legendas_idiomas, self._cfg,
            caminho_saida=Path(f"legendas_{self._cfg.NOME_ORACAO}.ass"),
        )
        logger.info("   ASS gerado: %s", ass_path.name)

        video_final = Path(self._cfg.NOME_VIDEO_FINAL)
        queimar_legendas_ass(video_base, ass_path, video_final)
        logger.info("✅ Vídeo final: %s (%.2f MB)", video_final.name, video_final.stat().st_size / 1_048_576)

        self._drive.upload(video_final, self._cfg.pasta_assets_videos, "video/mp4")
        self._cp.salvar("legendas_queimadas", {"arquivo": str(video_final)})
        return video_final

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _carregar_todos_srts(self, legendas_pt: list[Legenda]) -> dict[str, list[Legenda]]:
        """Carrega SRTs de todos os idiomas, priorizando YouTube."""
        resultado: dict[str, list[Legenda]] = {"pt": legendas_pt}
        for lang in self._cfg.IDIOMAS:
            if lang == "pt":
                continue
            # Priorizar YouTube
            srt_path = Path(self._cfg.nome_srt(lang))
            if srt_path.exists():
                resultado[lang] = ler_srt(srt_path)
                logger.info("   📺 %s: usando SRT do YouTube (%d segmentos)", lang.upper(), len(resultado[lang]))
            else:
                # Fallback: usar PT traduzido
                logger.warning("   ⚠️ %s: SRT não encontrado, usando PT como fallback", lang.upper())
                resultado[lang] = legendas_pt
        return resultado

    def _carregar_classificacoes(self, legendas_idiomas: dict[str, list[Legenda]]) -> dict[str, list[Legenda]]:
        """Carrega classificações para legendas já em memória (checkpoint skip)."""
        self._clf.invalidar_cache()
        for lang, legendas in legendas_idiomas.items():
            # Tenta baixar do Drive de IDs se não existir localmente
            json_local = Path(self._clf._nome_json(lang))
            if not json_local.exists() and not self._clf.existe_corrigido(lang):
                self._drive.download(self._cfg.pasta_assets_cache, self._clf._nome_json(lang), json_local)
            self._clf.carregar_para_legendas(legendas, lang)
        return legendas_idiomas

    def _clipes_do_checkpoint(self) -> list[Clipe]:
        meta = self._cp.metadados("clipes_cortados")
        return [
            Clipe(url="", autor=item.get("autor", "Pixabay"),
                  indice=item.get("indice", 0), arquivo_pronto=item.get("arquivo"))
            for item in meta.get("clipes", [])
        ]

    def limpar_temporarios(self) -> None:
        for pasta in ["clipes_cortados", "clipes_prontos", "temp_raw"]:
            p = Path(pasta)
            if p.exists():
                shutil.rmtree(p)
                logger.info("🗑️ %s/", pasta)
        for arq in ["logo_baixada.png", "video_com_audio.mp4", "video_sem_audio.mp4"]:
            p = Path(arq)
            if p.exists():
                p.unlink()
                logger.info("🗑️ %s", arq)

    # ── Instrução de revisão ──────────────────────────────────────────────────

    @staticmethod
    def _imprimir_instrucoes_revisao(pacote: Optional[Path], novos: list[str]) -> None:
        print("\n" + "━" * 65)
        print("⏸️  PAUSA — REVISÃO MANUAL NECESSÁRIA")
        print("━" * 65)
        if novos:
            print(f"\n  Idiomas com JSONs novos gerados: {', '.join(novos)}")
        print("""
  1. Acesse sua pasta no Drive:
       MyDrive/pai_nosso_refatorado_v1/pipeline/correcoes/<nome_oracao>/

  2. Você encontrará:
       • classificacao_*_pt/en/es/fr.json  ← JSONs a corrigir
       • relatorio_classificacoes.csv      ← visão consolidada
       • prompt_revisao.md                 ← cole numa IA (Claude/GPT)

  3. Corrija os JSONs com a IA e salve os arquivos corrigidos
     de volta na mesma pasta do Drive.

  4. Execute no notebook:
       legendas_idiomas = pipeline.fase5b_recarregar()
       video_final = pipeline.continuar()
""")
        print("━" * 65 + "\n")
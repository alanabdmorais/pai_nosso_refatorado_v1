# -*- coding: utf-8 -*-
"""
groq_client.py — Cliente Groq com retry e validação.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional, List

from models import Palavra

logger = logging.getLogger(__name__)


class GroqError(Exception):
    pass


class GroqClient:
    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile",
                 max_tentativas: int = 3, delay: float = 2.0,
                 nome_oracao: str = "") -> None:
        if not api_key:
            raise GroqError("GROQ_KEY não fornecida")
        
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        self.model = model
        self.max_tentativas = max_tentativas
        self.delay = delay
        self.nome_oracao = nome_oracao

    def corrigir_texto_pt(self, legendas):
        """Corrige o texto em português usando referência do YouTube se disponível."""
        from models import Legenda
        from srt_utils import ler_srt
        
        # Carregar referência do YouTube (se existir)
        referencia = ""
        ref_path = Path(f'{self.nome_oracao}_yt_ref_pt.srt') if self.nome_oracao else None
        
        if ref_path and ref_path.exists():
            # Lê o SRT de referência e extrai apenas o texto (sem timestamps)
            ref_legendas = ler_srt(ref_path)
            referencia = " ".join(leg.texto for leg in ref_legendas)
            print(f"   📺 Referência carregada: {ref_path.name} ({len(ref_legendas)} segmentos)")
            print(f"   📺 Texto de referência: {referencia[:200]}...")
        else:
            print(f"   📺 Nenhuma referência encontrada em: {ref_path if ref_path else 'não configurado'}")
            print(f"   💡 Dica: Baixe a legenda PT do YouTube na célula B0 para melhorar a correção")
        
        legendas_corrigidas = []
        
        for i, legenda in enumerate(legendas):
            print(f"   Corrigindo legenda {i+1}/{len(legendas)}: '{legenda.texto[:50]}...'")
            
            if referencia:
                PROMPT_CORRECAO = """Você é um revisor de textos profissional especializado em orações religiosas.

## REFERÊNCIA OFICIAL (legenda do YouTube):
{referencia}

## TAREFA:
Compare o texto do Whisper com a referência oficial e corrija:
- Erros de concordância verbal e nominal (ex: "santificados" → "santificado")
- Erros de ortografia (ex: "Perdua aí" → "Perdoai")
- Pontuação inadequada
- Maiúsculas/minúsculas
- Pequenas variações de palavras (ex: "Vem" → "Venha", "nos dá" → "nos dai")

REGRAS:
- USE a referência como guia principal para corrigir o texto
- Mantenha a estrutura de segmentação do Whisper (não junte frases)
- Mantenha o estilo solene da oração
- Devolva APENAS o texto corrigido, sem explicações

TEXTO DO WHISPER: {texto}

TEXTO CORRIGIDO:"""
                
                prompt = PROMPT_CORRECAO.format(referencia=referencia[:2000], texto=legenda.texto)
                system_prompt = "Você é um revisor de textos profissional especializado em orações religiosas."
            else:
                PROMPT_CORRECAO = """Você é um revisor de textos profissional.

Corrija o texto abaixo:
- Erros de concordância verbal e nominal
- Erros de ortografia
- Pontuação inadequada
- Maiúsculas/minúsculas

REGRAS:
- Mantenha o sentido original
- Devolva APENAS o texto corrigido

TEXTO: {texto}

TEXTO CORRIGIDO:"""
                
                prompt = PROMPT_CORRECAO.format(texto=legenda.texto)
                system_prompt = "Você é um revisor de textos profissional."
            
            try:
                texto_corrigido = self._call_text(prompt, system_prompt)
                
                nova_legenda = Legenda(
                    id=legenda.id,
                    inicio_ms=legenda.inicio_ms,
                    fim_ms=legenda.fim_ms,
                    texto=texto_corrigido,
                    palavras=[]
                )
                legendas_corrigidas.append(nova_legenda)
                
            except Exception as e:
                print(f"      ⚠️ Erro: {e}")
                legendas_corrigidas.append(legenda)
            
            time.sleep(0.5)
        
        return legendas_corrigidas

    def redistribuir_traducoes(self, texto_corrido: str, legendas_pt: list, lang: str) -> list[str]:
        """Redistribui o texto traduzido nos mesmos segmentos do PT."""
        from models import Legenda
        
        PROMPT_REDISTRIBUICAO = f"""Você é um especialista em alinhamento de legendas multilíngues.

TEXTO COMPLETO EM {lang.upper()}:
{texto_corrido[:1500]}

O texto acima deve ser dividido em EXATAMENTE {len(legendas_pt)} segmentos,
seguindo os cortes semânticos do português.

REGRAS:
- Mantenha o sentido litúrgico e naturalidade no idioma de destino
- Cada segmento deve ser uma frase completa e com sentido próprio
- Mantenha a ordem cronológica do texto original
- Retorne APENAS um JSON no formato: ["segmento1", "segmento2", ...]

Segmentos em português (referência de corte):
{chr(10).join([f'{i+1}. {leg.texto[:80]}' for i, leg in enumerate(legendas_pt[:len(legendas_pt)])])}

Retorne SOMENTE o JSON com os {len(legendas_pt)} segmentos traduzidos."""
        
        try:
            resultado = self._call_json(PROMPT_REDISTRIBUICAO, "Especialista em alinhamento de legendas")
            if isinstance(resultado, list) and len(resultado) == len(legendas_pt):
                return resultado
            else:
                logger.warning(f"Redistribuição falhou, usando fallback")
                return [texto_corrido[:200]] * len(legendas_pt)
        except Exception as e:
            logger.warning(f"Erro na redistribuição: {e}")
            return [texto_corrido[:200]] * len(legendas_pt)

    def revisar_vocabulario_liturgico(self, segmentos: list[str], lang: str) -> list[str]:
        """Revisa vocabulário litúrgico específico do idioma."""
        from constants import EXEMPLOS_LITURGICOS
        
        exemplos = EXEMPLOS_LITURGICOS.get(lang, "")
        
        PROMPT_REVISAO = f"""Você é um especialista em textos litúrgicos em {lang.upper()}.

Revise os segmentos abaixo para usar o vocabulário litúrgico correto.

EXEMPLOS DE VOCABULÁRIO LITÚRGICO CORRETO:
{exemplos}

REGRAS:
- Use formas arcaicas/solemes quando apropriado (ex: "thy", "thine" em inglês)
- Mantenha a tradução tradicional da oração
- Corrija apenas vocabulário, não mude a estrutura
- Retorne APENAS os segmentos revisados, um por linha

SEGMENTOS ORIGINAIS:
{chr(10).join(segmentos)}

SEGMENTOS REVISADOS:"""
        
        try:
            texto = self._call_text(PROMPT_REVISAO, "Especialista em textos litúrgicos", max_tokens=2000)
            revisados = [l.strip() for l in texto.strip().split('\n') if l.strip()]
            if len(revisados) == len(segmentos):
                return revisados
        except Exception as e:
            logger.warning(f"Revisão litúrgica falhou: {e}")
        
        return segmentos

    def classificar_legenda(self, texto: str, lang: str) -> list[Palavra]:
        PROMPT_SISTEMA = """Você é especialista em linguística.
Classifique cada palavra usando SOMENTE as classes fornecidas.

REGRAS OBRIGATÓRIAS:
1. A palavra 'que' em PT/ES/FR é SEMPRE pronome_relativo (NUNCA conjuncao)
2. 'thy' em INGLÊS é pronome_possessivo_singular (NUNCA pronome_pessoal)
3. 'tu' em espanhol antes de substantivo é pronome_possessivo_singular
4. Verbos no infinitivo são verbo_presente
5. Subjuntivo em francês é verbo_subjuntivo

Responda APENAS com JSON: {"palavras": [{"texto": "palavra", "classe": "classe"}]}"""

        user = f"Idioma: {lang}\nLegenda: {texto}"
        
        try:
            resultado = self._call_json(user, PROMPT_SISTEMA, max_tokens=600)
            palavras_raw = resultado.get("palavras", []) if isinstance(resultado, dict) else []
            
            palavras = []
            for p in palavras_raw:
                texto_p = str(p.get("texto", "")).strip()
                classe_p = str(p.get("classe", "")).strip().lower()
                if texto_p and texto_p not in self._ARTEFATOS:
                    palavras.append(Palavra(texto=texto_p, classe=classe_p))
            
            if palavras:
                return palavras
        except Exception as e:
            logger.warning(f"Erro na classificação: {e}")
        
        return self._fallback_palavras(texto)

    def limpar_artefatos(self, texto: str) -> str:
        """
        Corrige APENAS artefatos e erros óbvios do texto PT.
        NÃO reescreve a oração — mantém o sentido e número de palavras.

        Remove: "M.", "METRO", "[Música]", "[Aplausos]", letras soltas
        Corrige: pontuação, erros muito óbvios de digitação
        """
        PROMPT = (
            "Você é um limpador de legendas religiosas. Remova APENAS artefatos:\n\n"
            "REGRAS:\n"
            "- Remova palavras soltas como M., METRO, M\n"
            "- Remova textos entre colchetes: [Música], [Aplausos]\n"
            "- Corrija pontuação (vírgulas, pontos finais)\n"
            "- Corrija apenas erros MUITO ÓBVIOS (ex: 'Perdua aí' → 'Perdoai')\n"
            "- NÃO mude palavras que estão corretas\n"
            "- NÃO reescreva a frase\n"
            "- Devolva APENAS o texto limpo, sem aspas nem explicações\n\n"
            f"TEXTO ORIGINAL: {texto}\n\n"
            "TEXTO LIMPO:"
        )
        resultado = self._call_text(PROMPT, "Limpador de artefatos de legenda")
        # Fallback: se Groq falhar ou devolver algo muito diferente, retorna original
        if not resultado or len(resultado) > len(texto) * 1.5:
            logger.warning("limpar_artefatos: fallback para texto original")
            return texto
        return resultado

    def _call_text(self, user_prompt: str, system_prompt: str, max_tokens: int = 300) -> str:
        for tentativa in range(1, self.max_tentativas + 1):
            try:
                resposta = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                    max_tokens=max_tokens,
                )
                texto = resposta.choices[0].message.content.strip()
                time.sleep(self.delay)
                return texto
            except Exception as exc:
                logger.warning("Tentativa %d/%d: %s", tentativa, self.max_tentativas, str(exc)[:80])
                if tentativa < self.max_tentativas:
                    time.sleep(self.delay * tentativa)
        
        raise GroqError("Falha após todas as tentativas")

    def _call_json(self, user_prompt: str, system_prompt: str, max_tokens: int = 1000) -> dict | list:
        for tentativa in range(1, self.max_tentativas + 1):
            try:
                resposta = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.1,
                    max_tokens=max_tokens,
                )
                texto = resposta.choices[0].message.content.strip()
                time.sleep(self.delay)
                return self._parse_json(texto)
            except Exception as exc:
                logger.warning("Tentativa %d/%d: %s", tentativa, self.max_tentativas, str(exc)[:80])
                if tentativa < self.max_tentativas:
                    time.sleep(self.delay * tentativa)
        
        raise GroqError("Falha após todas as tentativas")

    def _parse_json(self, texto: str) -> dict | list:
        limpo = re.sub(r"```json|```", "", texto).strip()
        try:
            return json.loads(limpo)
        except json.JSONDecodeError:
            match = re.search(r"(\[.*\]|\{.*\})", limpo, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise GroqError(f"JSON inválido: {limpo[:200]}")

    # Tokens que são artefatos de transcrição e não devem virar palavras classificadas
    _ARTEFATOS: frozenset[str] = frozenset({"M", "M.", "METRO", "m", "Amen.", "Amem."})

    def _fallback_palavras(self, texto: str) -> list[Palavra]:
        """Fallback quando o Groq falha: tokeniza e atribui classe genérica válida."""
        return [
            Palavra(texto=t, classe="substantivo_masculino_singular")
            for t in texto.split()
            if t and t not in self._ARTEFATOS
        ]
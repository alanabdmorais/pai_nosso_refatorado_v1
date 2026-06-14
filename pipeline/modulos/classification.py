# -*- coding: utf-8 -*-
"""
classification.py — Classificação morfológica com fluxo de revisão manual.

FLUXO DA ESTRATÉGIA INTERMEDIÁRIA:
  1. Groq classifica → JSON salvo localmente e no Drive (pasta bruta)
  2. Pipeline exporta pacote de revisão: JSONs + CSV + prompt pronto para IA
  3. Usuário corrige com IA externa e coloca JSONs corrigidos na pasta Drive
  4. Pipeline carrega dos JSONs corrigidos e continua

PRIORIDADE DE CARREGAMENTO (do mais confiável para o menos):
  Drive (corrigidos) > Local (bruto do Groq) > Groq (nova chamada)

A pasta de correções no Drive é separada da pasta de backup:
  correcoes/  ← usuário coloca JSONs revisados aqui
  brutos/     ← pipeline salva automaticamente após Groq
"""
from __future__ import annotations

import csv
import json
import logging
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ClassificationError(Exception):
    """Erro na classificação morfológica."""


class Classifier:
    """
    Gerencia o ciclo completo de classificação morfológica:
    geração via Groq → exportação para revisão → carregamento dos corrigidos.
    """

    def __init__(self, config, groq) -> None:
        self._cfg  = config
        self._groq = groq

        # Pasta no Drive montado onde o usuário coloca os JSONs já revisados pela IA
        self.pasta_correcoes = Path(
            f"/content/drive/MyDrive/pai_nosso_refatorado_v1/pipeline/correcoes/{self._cfg.NOME_ORACAO}"
        )
        # Pasta onde o pipeline salva os JSONs brutos gerados pelo Groq (backup)
        self.pasta_brutos = Path(
            f"/content/drive/MyDrive/pai_nosso_refatorado_v1/pipeline/brutos/{self._cfg.NOME_ORACAO}"
        )
        # Pasta local de trabalho no Colab
        self.pasta_local = Path("/content")

        self._cache: dict[str, dict] = {}

    # ── Nomes de arquivo ──────────────────────────────────────────────────────

    def _nome_json(self, lang: str) -> str:
        return f"classificacao_{self._cfg.NOME_ORACAO}_{lang}.json"

    # ── Verificação de disponibilidade ────────────────────────────────────────

    def existe_corrigido(self, lang: str) -> bool:
        """Verifica se há um JSON revisado pelo usuário na pasta Drive."""
        return (self.pasta_correcoes / self._nome_json(lang)).exists()

    def existe_bruto(self, lang: str) -> bool:
        """Verifica se há um JSON bruto (do Groq) localmente."""
        return (self.pasta_local / self._nome_json(lang)).exists()

    def status(self, idiomas: Optional[list[str]] = None) -> dict[str, str]:
        """
        Retorna o status de cada idioma.
        Valores: 'corrigido' | 'bruto' | 'ausente'
        """
        idiomas = idiomas or self._cfg.IDIOMAS
        return {
            lang: (
                "corrigido" if self.existe_corrigido(lang) else
                "bruto"     if self.existe_bruto(lang) else
                "ausente"
            )
            for lang in idiomas
        }

    def imprimir_status(self) -> None:
        """Imprime painel de status legível para o usuário."""
        icones = {"corrigido": "✅ Drive (revisado)", "bruto": "⚠️  Local (bruto Groq)", "ausente": "❌ Ausente"}
        print("\n📊 Status das classificações:")
        print("─" * 45)
        for lang, estado in self.status().items():
            print(f"   {lang.upper()}  {icones[estado]}")
        print("─" * 45)

    # ── Carregamento ──────────────────────────────────────────────────────────

    def carregar_para_legendas(self, legendas: list, lang: str) -> bool:
        """
        Carrega o JSON de classificação (corrigido ou bruto) e preenche
        leg.palavras em cada Legenda. Retorna True se bem-sucedido.

        CORREÇÃO DO BUG ANTERIOR: preenche leg.palavras do zero a partir
        do JSON, sem depender de palavras pré-existentes na legenda.
        """
        from models import Palavra

        dados = self._carregar_json(lang)
        if not dados:
            return False

        # Mapeia id → lista de Palavra
        mapa: dict[int, list[Palavra]] = {}
        for chave, entrada in dados.items():
            try:
                lid = int(chave)
            except ValueError:
                continue
            mapa[lid] = [
                Palavra(texto=p["texto"], classe=self._normalizar_classe(p["classe"], p["texto"], lang))
                for p in entrada.get("palavras", [])
                if p.get("texto")
            ]

        cobertura = sum(1 for leg in legendas if leg.id in mapa and mapa[leg.id])
        if cobertura == 0:
            logger.warning("JSON de %s sem cobertura — ignorando", lang.upper())
            return False

        for leg in legendas:
            if leg.id in mapa:
                leg.palavras = mapa[leg.id]

        origem = "Drive (corrigido)" if self.existe_corrigido(lang) else "local (bruto)"
        logger.info("   ✅ %s: %d/%d legendas carregadas do %s", lang.upper(), cobertura, len(legendas), origem)
        return True

    def _carregar_json(self, lang: str) -> Optional[dict]:
        """Carrega JSON com prioridade: Drive corrigido > local bruto."""
        if lang in self._cache:
            return self._cache[lang]

        # 1. Drive (revisado pelo usuário)
        caminho_drive = self.pasta_correcoes / self._nome_json(lang)
        if caminho_drive.exists():
            dados = self._ler_json(caminho_drive)
            if dados:
                self._cache[lang] = dados
                logger.info("   📁 %s: carregando Drive (corrigido)", lang.upper())
                return dados

        # 2. Local (bruto do Groq)
        caminho_local = self.pasta_local / self._nome_json(lang)
        if caminho_local.exists():
            dados = self._ler_json(caminho_local)
            if dados:
                self._cache[lang] = dados
                logger.info("   📁 %s: carregando local (bruto Groq)", lang.upper())
                return dados

        return None

    @staticmethod
    def _ler_json(caminho: Path) -> Optional[dict]:
        try:
            return json.loads(caminho.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("JSON ilegível (%s): %s", caminho.name, exc)
            return None

    # ── Normalização de classes ───────────────────────────────────────────────

    def _normalizar_classe(self, classe: str, texto: str = "", lang: str = "") -> str:
        """
        Normaliza a classe retornada pelo Groq ou pela IA de revisão.
        Aplica mapeamentos de compatibilidade definidos em constants.py.
        """
        from constants import MAPEAMENTO_CLASSES, CORRECOES_GLOBAIS, CORRECOES_POR_IDIOMA, CORES_HTML

        texto_lower = texto.lower().strip()

        # Correção por palavra global
        if texto_lower in CORRECOES_GLOBAIS:
            return CORRECOES_GLOBAIS[texto_lower]

        # Correção por idioma
        if lang in CORRECOES_POR_IDIOMA and texto_lower in CORRECOES_POR_IDIOMA[lang]:
            return CORRECOES_POR_IDIOMA[lang][texto_lower]

        # Mapeamento de classe (ex: verbo_infinito → verbo_presente)
        classe_norm = MAPEAMENTO_CLASSES.get(classe, classe)

        # Se ainda inválida, usa fallback visível
        if classe_norm not in CORES_HTML:
            logger.warning("Classe sem cor: '%s' (palavra: '%s') → fallback", classe_norm, texto)
            return "substantivo_masculino_singular"

        return classe_norm

    # ── Classificação via Groq ────────────────────────────────────────────────

    def classificar_idioma(self, legendas: list, lang: str, forcar: bool = False) -> list:
        """
        Classifica morfologicamente via Groq e salva o JSON bruto.
        Só chama o Groq se não houver cache (ou se forcar=True).
        """
        if not forcar and (self.existe_corrigido(lang) or self.existe_bruto(lang)):
            self.carregar_para_legendas(legendas, lang)
            return legendas

        logger.info("   🤖 %s: classificando via Groq...", lang.upper())
        for i, leg in enumerate(legendas):
            logger.info("      [%d/%d] '%s'", i + 1, len(legendas), leg.texto[:50])
            leg.palavras = self._groq.classificar_legenda(leg.texto, lang)
            time.sleep(0.3)

        self.salvar_json(legendas, lang)
        return legendas

    # ── Persistência ──────────────────────────────────────────────────────────

    def salvar_json(self, legendas: list, lang: str) -> Path:
        """Salva JSON localmente e faz backup na pasta brutos/ do Drive."""
        dados: dict[str, dict] = {}
        for leg in legendas:
            dados[str(leg.id)] = {
                "inicio":         leg.inicio_str,
                "fim":            leg.fim_str,
                "texto_original": leg.texto,
                "palavras": [
                    {"texto": p.texto, "classe": p.classe}
                    for p in leg.palavras
                ],
            }

        # Salvar local
        caminho_local = self.pasta_local / self._nome_json(lang)
        caminho_local.write_text(
            json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("   💾 Salvo local: %s", caminho_local.name)

        # Backup no Drive (pasta brutos)
        try:
            self.pasta_brutos.mkdir(parents=True, exist_ok=True)
            shutil.copy(caminho_local, self.pasta_brutos / self._nome_json(lang))
            logger.info("   ☁️  Backup Drive: brutos/%s/%s", self._cfg.NOME_ORACAO, self._nome_json(lang))
        except Exception as exc:
            logger.warning("   ⚠️  Backup Drive falhou: %s", exc)

        self._cache[lang] = dados
        return caminho_local

    def invalidar_cache(self, lang: Optional[str] = None) -> None:
        """Invalida o cache em memória (força releitura do disco na próxima vez)."""
        if lang:
            self._cache.pop(lang, None)
            logger.info("🗑️ Cache invalidado: %s", lang.upper())
        else:
            self._cache.clear()
            logger.info("🗑️ Cache completo invalidado")

    # ── Exportação do pacote de revisão (CORRIGIDO: guias na raiz) ────────────

    def exportar_pacote_revisao(self, legendas_idiomas: dict) -> Path:
        """
        Gera o pacote completo para revisão manual pela IA:
          - prompt_revisao.md   → SALVA NA RAIZ de correcoes/ (genérico)
          - relatorio_classificacoes.csv → SALVA NA RAIZ de correcoes/ (genérico)
          - JSONs → SALVA DENTRO de correcoes/{NOME_ORACAO}/

        Retorna o caminho da pasta onde os JSONs foram salvos.
        """
        NOME_ORACAO = self._cfg.NOME_ORACAO
        
        # Pastas do Drive
        pasta_correcoes_root = Path("/content/drive/MyDrive/pai_nosso_refatorado_v1/pipeline/correcoes")
        pasta_oracao = pasta_correcoes_root / NOME_ORACAO
        pasta_oracao.mkdir(parents=True, exist_ok=True)

        # Pasta local temporária
        pasta_pacote = self.pasta_local / f"pacote_revisao_{NOME_ORACAO}"
        pasta_pacote.mkdir(exist_ok=True)

        # 1. Copia os JSONs brutos para o pacote local e para a pasta da oração no Drive
        for lang in self._cfg.IDIOMAS:
            src = self.pasta_local / self._nome_json(lang)
            if src.exists():
                shutil.copy(src, pasta_pacote / self._nome_json(lang))
                shutil.copy(src, pasta_oracao / self._nome_json(lang))
                logger.info("   📁 JSON %s copiado para %s", lang.upper(), pasta_oracao)

        # 2. Gera CSV (na raiz de correcoes/)
        csv_path_root = pasta_correcoes_root / "relatorio_classificacoes.csv"
        self._gerar_csv(legendas_idiomas, csv_path_root)

        # 3. Gera prompt de revisão (na raiz de correcoes/)
        prompt_path_root = pasta_correcoes_root / "prompt_revisao.md"
        self._gerar_prompt_revisao(prompt_path_root)

        # 4. Também mantém uma cópia local para referência
        shutil.copy(csv_path_root, pasta_pacote / "relatorio_classificacoes.csv")
        shutil.copy(prompt_path_root, pasta_pacote / "prompt_revisao.md")

        logger.info("📦 Pacote de revisão: JSONs em %s", pasta_oracao)
        logger.info("📄 Guias (prompt + CSV) em: %s", pasta_correcoes_root)
        return pasta_oracao

    def _gerar_csv(self, legendas_idiomas: dict, caminho: Path) -> None:
        """Gera CSV consolidado com todas as classificações de todos os idiomas.
        
        Inclui coluna 'Sugestao' para classes inválidas, facilitando revisão manual.
        """
        from constants import CORES_HTML, MAPEAMENTO_CLASSES

        with open(caminho, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Idioma", "Legenda", "Palavra", "Classe", "Cor_Hex", "Valida", "Sugestao"
            ])

            for lang, legendas in legendas_idiomas.items():
                for leg in legendas:
                    for p in leg.palavras:
                        cor    = CORES_HTML.get(p.classe, "")
                        valida = "SIM" if p.classe in CORES_HTML else "NÃO"
                        # Sugere correção automática quando a classe está no mapeamento
                        sugestao = ""
                        if valida == "NÃO":
                            sugestao = MAPEAMENTO_CLASSES.get(p.classe, "")
                            if not sugestao:
                                # Heurísticas básicas para classes comuns sem mapeamento
                                if p.classe in ("substantivo", "noun"):
                                    sugestao = "substantivo_masculino_singular OU substantivo_feminino_singular"
                                elif p.classe in ("advérbio", "adverb", "adverbio_normal"):
                                    sugestao = "advérbio_normal"
                                elif p.classe in ("adjetivo", "adjective"):
                                    sugestao = "adjetivo_normal"
                                elif p.classe in ("artigo", "article"):
                                    sugestao = "artigo_definido OU artigo_indefinido"
                                elif p.classe in ("determinante", "determiner"):
                                    sugestao = "artigo_definido"
                                elif p.classe in ("participio_passado", "participe_passado",
                                                  "gerundio_participio"):
                                    sugestao = "verbo_passado"
                                elif p.classe in ("abreviatura",):
                                    sugestao = "— remover (artefato)"
                                elif p.classe in ("preposição",):  # acento errado
                                    sugestao = "preposicao"
                                elif p.classe in ("conjunção",):   # acento errado
                                    sugestao = "conjuncao"
                        writer.writerow([
                            lang.upper(), leg.id,
                            p.texto, p.classe, cor, valida, sugestao,
                        ])

        logger.info("📊 CSV gerado: %s", caminho.name)

    def _gerar_prompt_revisao(self, caminho: Path) -> None:
        """Gera o prompt completo para a IA revisora."""
        from constants import CORES_HTML

        # Classes agrupadas por categoria (mais fácil de ler do que lista flat com hex)
        categorias = {
            "SUBSTANTIVOS": sorted(c for c in CORES_HTML if c.startswith("substantivo")),
            "PRONOMES":     sorted(c for c in CORES_HTML if c.startswith("pronome")),
            "VERBOS":       sorted(c for c in CORES_HTML if c.startswith("verbo")),
            "ADJETIVOS":    sorted(c for c in CORES_HTML if c.startswith("adjetivo")),
            "ADVÉRBIOS":    sorted(c for c in CORES_HTML if c.startswith("advérbio")),
            "OUTROS":       sorted(
                c for c in CORES_HTML
                if not any(c.startswith(p) for p in
                           ("substantivo", "pronome", "verbo", "adjetivo", "advérbio"))
            ),
        }
        blocos = []
        for cat, lista in categorias.items():
            if lista:
                blocos.append(f"### {cat}")
                blocos.extend(f"- `{c}`" for c in lista)
        classes_md = "\n".join(blocos)

        data_hora = datetime.now().strftime("%Y-%m-%d %H:%M")
        nome = self._cfg.NOME_ORACAO

        prompt = f"""\
# Prompt de Revisão — Classificações Morfológicas
**Projeto:** `{nome}`  |  **Data:** {data_hora}

---

## Contexto

Você está revisando classificações morfológicas de legendas de "{nome}" em 4 idiomas:
**PT** (português), **EN** (inglês), **ES** (espanhol), **FR** (francês).

As classificações foram geradas automaticamente pelo modelo Groq e contêm erros.
Cada palavra aparece colorida no vídeo final de acordo com sua classe gramatical —
uma classe errada significa cor errada na legenda.

**O CSV `relatorio_classificacoes.csv` mostra todas as palavras com coluna `Valida`.**
Palavras com `Valida = NÃO` obrigatoriamente precisam ser corrigidas.
A coluna `Sugestao` já indica a correção provável para a maioria dos casos.

---

## Sua Tarefa

Corrija os 4 arquivos JSON:
- `classificacao_{nome}_pt.json`
- `classificacao_{nome}_en.json`
- `classificacao_{nome}_es.json`
- `classificacao_{nome}_fr.json`

**Regras obrigatórias:**
1. Use **SOMENTE** as classes listadas na seção "Classes Válidas" abaixo.
2. Mantenha a estrutura JSON exata — não remova nem adicione campos.
3. Não altere `inicio`, `fim` ou `texto_original`.
4. Palavras marcadas `Valida = NÃO` no CSV **devem** ter a classe corrigida.
5. Palavras que são artefatos de transcrição (ex: `"M"`, `"METRO"`) → remova-as da lista `palavras`.

---

## Erros Frequentes do Groq (corrija sempre que encontrar)

| Classe incorreta | Classe correta |
|---|---|
| `substantivo` | `substantivo_masculino_singular` ou `substantivo_feminino_singular` |
| `advérbio` | `advérbio_normal` |
| `adjetivo` | `adjetivo_normal` |
| `artigo` | `artigo_definido` ou `artigo_indefinido` |
| `determinante` | `artigo_definido` |
| `participio_passado` | `verbo_passado` |
| `participe_passado` | `verbo_passado` |
| `verbo_infinito` | `verbo_presente` |
| `subjonctif_fr` | `verbo_subjuntivo` |
| `preposição` (com acento) | `preposicao` (sem acento) |
| `conjunção` (com acento) | `conjuncao` (sem acento) |
| `abreviatura` | — remover a palavra da lista |

---

## Regras Linguísticas por Idioma

**PT/ES/FR — `que` / `qui`:**
- "Pai nosso **que** estais...", "Padre nuestro **que** estás...", "Notre Père **qui** es..." → `pronome_relativo`

**EN — pronomes arcaicos:**
- `thy`, `thine` → sempre `pronome_possessivo_singular`
- `art` (arcaico de "are") → `verbo_presente`

**ES — `tu` possessivo:**
- `tu` antes de substantivo ("**tu** nombre", "**tu** reino") → `pronome_possessivo_singular`

**FR — modo subjuntivo:**
- `soit` → `verbo_subjuntivo`
- `pardonnons` → `verbo_presente`

---

## Classes Válidas (use SOMENTE estas)

{classes_md}

---

## Formato de Saída Esperado

Devolva cada JSON corrigido mantendo esta estrutura exata:

```json
{{
  "1": {{
    "inicio": "00:00:00,000",
    "fim": "00:00:05,539",
    "texto_original": "Pai nosso que estais no céu, santificado seja o vosso nome.",
    "palavras": [
      {{"texto": "Pai",         "classe": "substantivo_masculino_singular"}},
      {{"texto": "nosso",       "classe": "pronome_possessivo_singular"}},
      {{"texto": "que",         "classe": "pronome_relativo"}},
      {{"texto": "estais",      "classe": "verbo_presente"}},
      {{"texto": "no",          "classe": "preposicao"}},
      {{"texto": "céu",         "classe": "substantivo_masculino_singular"}},
      {{"texto": "santificado", "classe": "verbo_presente"}},
      {{"texto": "seja",        "classe": "verbo_presente"}},
      {{"texto": "o",           "classe": "artigo_definido"}},
      {{"texto": "vosso",       "classe": "pronome_possessivo_singular"}},
      {{"texto": "nome",        "classe": "substantivo_masculino_singular"}}
    ]
  }}
}}
```

---

## Como Entregar

Após corrigir, salve os 4 JSONs revisados na pasta do Drive:
`MyDrive/pai_nosso_refatorado_v1/pipeline/correcoes/{nome}/`

Com os nomes originais:
- `classificacao_{nome}_pt.json`
- `classificacao_{nome}_en.json`
- `classificacao_{nome}_es.json`
- `classificacao_{nome}_fr.json`

Depois execute a célula **"▶ FASE 5C — Recarregar classificações corrigidas"** no notebook.
"""
        caminho.write_text(prompt, encoding="utf-8")
        logger.info("📝 Prompt de revisão gerado: %s", caminho.name)

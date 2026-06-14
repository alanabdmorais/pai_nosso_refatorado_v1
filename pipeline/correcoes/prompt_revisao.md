# Prompt de Revisão — Classificações Morfológicas
**Projeto:** `pai_nosso`  |  **Data:** 2026-06-14 22:01

---

## Contexto

Você está revisando classificações morfológicas de legendas de "pai_nosso" em 4 idiomas:
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
- `classificacao_pai_nosso_pt.json`
- `classificacao_pai_nosso_en.json`
- `classificacao_pai_nosso_es.json`
- `classificacao_pai_nosso_fr.json`

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

### SUBSTANTIVOS
- `substantivo_feminino_plural`
- `substantivo_feminino_singular`
- `substantivo_masculino_plural`
- `substantivo_masculino_singular`
### PRONOMES
- `pronome_adverbial`
- `pronome_demonstrativo`
- `pronome_indefinido`
- `pronome_interrogativo`
- `pronome_it`
- `pronome_objeto`
- `pronome_obliquo`
- `pronome_pessoal`
- `pronome_possessivo_plural`
- `pronome_possessivo_singular`
- `pronome_reflexivo`
- `pronome_relativo`
### VERBOS
- `verbo_auxiliar`
- `verbo_condicional`
- `verbo_futuro`
- `verbo_futuro_proximo`
- `verbo_gerundio`
- `verbo_imperativo`
- `verbo_infinito`
- `verbo_modal`
- `verbo_passado`
- `verbo_presente`
- `verbo_subjuntivo`
### ADJETIVOS
- `adjetivo_comparativo`
- `adjetivo_normal`
- `adjetivo_superlativo`
### ADVÉRBIOS
- `advérbio_intensificador`
- `advérbio_normal`
### OUTROS
- `artigo_definido`
- `artigo_indefinido`
- `artigo_partitivo`
- `colocacao_pronominal`
- `comparativo_superlativo`
- `concordancia_adjetivo`
- `conditionnel`
- `conjuncao`
- `futur_proche`
- `futuro_going_to`
- `futuro_subjuntivo`
- `gerundio_participio`
- `imparfait`
- `imperativo_pronome`
- `interjeicao`
- `lo_neutro`
- `passe_compose`
- `plus_que_parfait`
- `preposicao`
- `preterito_perfecto`
- `se_impessoal`
- `subjonctif_fr`
- `subjuntivo_es`
- `usted`
- `vos_portugues`
- `voseo`

---

## Formato de Saída Esperado

Devolva cada JSON corrigido mantendo esta estrutura exata:

```json
{
  "1": {
    "inicio": "00:00:00,000",
    "fim": "00:00:05,539",
    "texto_original": "Pai nosso que estais no céu, santificado seja o vosso nome.",
    "palavras": [
      {"texto": "Pai",         "classe": "substantivo_masculino_singular"},
      {"texto": "nosso",       "classe": "pronome_possessivo_singular"},
      {"texto": "que",         "classe": "pronome_relativo"},
      {"texto": "estais",      "classe": "verbo_presente"},
      {"texto": "no",          "classe": "preposicao"},
      {"texto": "céu",         "classe": "substantivo_masculino_singular"},
      {"texto": "santificado", "classe": "verbo_presente"},
      {"texto": "seja",        "classe": "verbo_presente"},
      {"texto": "o",           "classe": "artigo_definido"},
      {"texto": "vosso",       "classe": "pronome_possessivo_singular"},
      {"texto": "nome",        "classe": "substantivo_masculino_singular"}
    ]
  }
}
```

---

## Como Entregar

Após corrigir, salve os 4 JSONs revisados na pasta do Drive:
`MyDrive/pai_nosso_refatorado_v1/pipeline/correcoes/pai_nosso/`

Com os nomes originais:
- `classificacao_pai_nosso_pt.json`
- `classificacao_pai_nosso_en.json`
- `classificacao_pai_nosso_es.json`
- `classificacao_pai_nosso_fr.json`

Depois execute a célula **"▶ FASE 5C — Recarregar classificações corrigidas"** no notebook.

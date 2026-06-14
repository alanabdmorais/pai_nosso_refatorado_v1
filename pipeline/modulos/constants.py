# -*- coding: utf-8 -*-
"""
constants.py — Constantes imutáveis do pipeline.
BASE CORRIGIDA - Funciona para QUALQUER ORAÇÃO
"""

# ── Idiomas suportados ────────────────────────────────────────────────────────
IDIOMAS: list[str] = ["pt", "en", "es", "fr"]

SIGLAS_IDIOMAS: dict[str, str] = {
    "pt": "PT-BR",
    "en": "EN-US",
    "es": "ES-ES",
    "fr": "FR-FR",
}

NOMES_IDIOMA: dict[str, str] = {
    "pt": "português",
    "en": "inglês",
    "es": "espanhol",
    "fr": "francês",
}

# ── Posições das legendas na tela (pixels, tela 1280px) ──────────────────────
POSICOES_Y: dict[str, int] = {"pt": 100, "en": 180, "es": 260, "fr": 340}
POS_SIGLA_Y: dict[str, int] = {"pt": 65, "en": 145, "es": 225, "fr": 305}

# ── Dimensões da tela ─────────────────────────────────────────────────────────
LARGURA_TELA: int = 1280
ALTURA_TELA: int = 720
CENTRO_X: int = LARGURA_TELA // 2

# ── Fontes e layout ───────────────────────────────────────────────────────────
TAMANHO_FONTE_TAG: int = 24
TAMANHO_FONTE_SIGLA: int = 20
BOX_BORDER: int = 6
ESPACAMENTO_PALAVRA: int = 40
LARGURA_CHAR: int = 12

# ── CORES DAS CLASSES GRAMATICAIS (HTML #RRGGBB) ──────────────────────────────
CORES_HTML: dict[str, str] = {
    # SUBSTANTIVOS
    "substantivo_masculino_singular": "#4169E1",
    "substantivo_masculino_plural":   "#1E3A8A",
    "substantivo_feminino_singular":  "#FF1493",
    "substantivo_feminino_plural":    "#C71585",
    # PRONOMES
    "pronome_possessivo_singular":    "#006400",
    "pronome_possessivo_plural":      "#004D00",
    "pronome_relativo":               "#FFD700",
    "pronome_pessoal":                "#008080",
    "pronome_indefinido":             "#20B2AA",
    "pronome_demonstrativo":          "#9370DB",
    "pronome_interrogativo":          "#FF6347",
    "pronome_reflexivo":              "#2E8B57",
    "pronome_objeto":                 "#87CEEB",
    "pronome_obliquo":                "#000080",
    # VERBOS
    "verbo_presente":                 "#9B59B6",
    "verbo_passado":                  "#4A235A",
    "verbo_futuro":                   "#1ABC9C",
    "verbo_imperativo":               "#E67E22",
    "verbo_condicional":              "#F39C12",
    "verbo_subjuntivo":               "#8E44AD",
    "verbo_gerundio":                 "#D35400",
    "verbo_modal":                    "#E6E6FA",
    "verbo_auxiliar":                 "#3498DB",
    "verbo_futuro_proximo":           "#32CD32",
    "verbo_infinito":                 "#9B59B6",      # mesma do presente
    # ADJETIVOS
    "adjetivo_normal":                "#E74C3C",
    "adjetivo_comparativo":           "#CC5500",
    "adjetivo_superlativo":           "#B22222",
    # ADVÉRBIOS
    "advérbio_normal":                "#16A085",
    "advérbio_intensificador":        "#27AE60",
    # OUTROS
    "preposicao":                     "#FF8C00",
    "artigo_definido":                "#D3D3D3",
    "artigo_indefinido":              "#BDC3C7",
    "conjuncao":                      "#8B4513",
    "interjeicao":                    "#FF69B4",
    # PARTICULARIDADES
    "futuro_going_to":                "#32CD32",
    "comparativo_superlativo":        "#8B0000",
    "pronome_it":                     "#A9A9A9",
    "usted":                          "#DDA0DD",
    "voseo":                          "#FFA500",
    "lo_neutro":                      "#C0C0C0",
    "se_impessoal":                   "#98FB98",
    "preterito_perfecto":             "#8B008B",
    "subjuntivo_es":                  "#FF7F50",
    "imperativo_pronome":             "#CC5500",
    "passe_compose":                  "#BA55D3",
    "imparfait":                      "#C39BD3",
    "plus_que_parfait":               "#4A235A",
    "subjonctif_fr":                  "#8E44AD",      # mesma do subjuntivo
    "conditionnel":                   "#B8860B",
    "futur_proche":                   "#90EE90",
    "pronome_adverbial":              "#89CFF0",
    "artigo_partitivo":               "#EAEAEA",
    "concordancia_adjetivo":          "#FF00FF",
    "vos_portugues":                  "#009C3B",
    "colocacao_pronominal":           "#F28500",
    "futuro_subjuntivo":              "#8B0000",
    "gerundio_participio":            "#800080",
}

# Cores que usam texto PRETO (fundos claros)
TEXTO_PRETO: set[str] = {
    "pronome_relativo", "artigo_definido", "artigo_indefinido",
    "verbo_modal", "pronome_it", "usted", "lo_neutro", "se_impessoal",
    "imparfait", "futur_proche", "pronome_adverbial", "artigo_partitivo",
}

# ── MAPEAMENTO DE NORMALIZAÇÃO (inglês → português) ───────────────────────────
MAPEAMENTO_CLASSES: dict[str, str] = {
    "noun": "substantivo_masculino_singular",
    "verb": "verbo_presente",
    "pronoun": "pronome_pessoal",
    "preposition": "preposicao",
    "adjective": "adjetivo_normal",
    "adverb": "advérbio_normal",
    "conjunction": "conjuncao",
    "determiner": "artigo_definido",
    "article": "artigo_definido",
    "interjection": "interjeicao",
    "possessive_pronoun": "pronome_possessivo_singular",
    "relative_pronoun": "pronome_relativo",
    "personal_pronoun": "pronome_pessoal",
    "present_verb": "verbo_presente",
    "past_verb": "verbo_passado",
    "modal_verb": "verbo_modal",
    "auxiliary_verb": "verbo_auxiliar",
    "gerund": "verbo_gerundio",
    "participle": "gerundio_participio",
    "adverbio_normal": "advérbio_normal",
    "conjunção": "conjuncao",
    "verbo_infinito": "verbo_presente",
    "subjonctif_fr": "verbo_subjuntivo",
}

# ── CORREÇÕES AUTOMÁTICAS POR PALAVRA (QUALQUER IDIOMA) ───────────────────────
CORRECOES_GLOBAIS: dict[str, str] = {
    "que": "pronome_relativo",      # PT, ES, FR
    "qui": "pronome_relativo",      # FR
    "which": "pronome_relativo",    # EN
    "who": "pronome_relativo",      # EN
    "that": "pronome_relativo",     # EN
    "como": "conjuncao",            # PT, ES
    "as": "conjuncao",              # EN
    "comme": "conjuncao",           # FR
    "thy": "pronome_possessivo_singular",   # EN
    "thine": "pronome_possessivo_singular", # EN
}

CORRECOES_POR_IDIOMA: dict[str, dict[str, str]] = {
    "es": {"tu": "pronome_possessivo_singular"},
    "fr": {"votre": "pronome_possessivo_singular", "notre": "pronome_possessivo_singular"},
    "pt": {"vosso": "pronome_possessivo_singular", "vossa": "pronome_possessivo_singular"},
}

# ── FUNÇÃO DE NORMALIZAÇÃO (usa as regras acima) ──────────────────────────────
def normalizar_classe(classe: str, palavra: str = "", idioma: str = "") -> str:
    """Normaliza classe gramatical aplicando correções automáticas."""
    palavra_lower = palavra.lower()
    
    # Correção por palavra (global)
    if palavra_lower in CORRECOES_GLOBAIS:
        return CORRECOES_GLOBAIS[palavra_lower]
    
    # Correção específica por idioma
    if idioma in CORRECOES_POR_IDIOMA and palavra_lower in CORRECOES_POR_IDIOMA[idioma]:
        return CORRECOES_POR_IDIOMA[idioma][palavra_lower]
    
    # Mapeamento geral
    return MAPEAMENTO_CLASSES.get(classe, classe)

# ── PROMPTS DO GROQ (OTIMIZADOS PARA QUALQUER ORAÇÃO) ─────────────────────────
PROMPT_SISTEMA_CORRECAO_PT = (
    "Você é um especialista em português e textos religiosos. "
    "Corrija APENAS erros de transcrição, mantendo a segmentação exata. "
    "Retorne SOMENTE um JSON válido. "
    'Formato: [{"id": 1, "texto": "frase corrigida"}, ...]'
)

PROMPT_SISTEMA_REDISTRIBUICAO = (
    "Você é um especialista em alinhamento de legendas multilíngues. "
    "Redistribua o texto em exatamente {N} segmentos seguindo os cortes do idioma de origem. "
    "Mantenha o sentido litúrgico e naturalidade no idioma de destino. "
    "Retorne SOMENTE um JSON válido. "
    'Formato: [{{"id": 1, "texto": "frase em {idioma}"}}]'
)

PROMPT_SISTEMA_CLASSIFICACAO = (
    "Você é um especialista em linguística. "
    "Classifique cada palavra da legenda usando SOMENTE as classes fornecidas. "
    "\n\nREGRAS OBRIGATÓRIAS (para TODOS os idiomas):"
    "\n1. A palavra 'que' em PT/ES/FR é SEMPRE pronome_relativo (NUNCA conjuncao)."
    "\n2. 'thy' em INGLÊS é pronome_possessivo_singular (NUNCA pronome_pessoal)."
    "\n3. 'tu' em espanhol antes de substantivo é pronome_possessivo_singular."
    "\n4. Verbos no infinitivo são verbo_presente."
    "\n5. Subjuntivo em francês é verbo_subjuntivo."
    "\n\nRetorne SOMENTE JSON. Formato: {{\"palavras\": [{{\"texto\": \"palavra\", \"classe\": \"classe\"}}]}}"
)

# ── FASES DO PIPELINE (checkpoint) ───────────────────────────────────────────
FASES_PIPELINE: list[str] = [
    "audio_gerado", "srt_pt_bruto", "srt_pt_corrigido",
    "srt_traduzidos", "classificacoes_feitas", "clipes_cortados",
    "video_base_criado", "legendas_queimadas",
]

# ── VOCABULÁRIO LITÚRGICO (para revisão) ─────────────────────────────────────
EXEMPLOS_LITURGICOS: dict[str, str] = {
    "en": "thy/thine/art/hallowed/trespass/forgive us our trespasses",
    "es": "santificado/venga/hágase/perdónanos/deudas/líbranos",
    "fr": "ton/que ton nom soit sanctifié/pardonne-nous/délivre-nous",
}
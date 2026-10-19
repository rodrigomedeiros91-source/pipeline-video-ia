import json
import os
from pathlib import Path

from fabrica import IDIOMAS

MAX_ORIGINAL_S = 15
FOLGA_MOMENTO_S = 5
MIN_NARRACAO = 0.40
DURACAO_MIN_S, DURACAO_MAX_S = 61, 90
JANELA_ANTES_S, JANELA_DEPOIS_S = 120, 60


def compactar_transcricao(palavras, max_palavras=30):
    """Agrupa palavras em linhas '[inicio] frase', quebrando em . ? ! ou a cada max_palavras."""
    linhas, atual = [], []
    for p in palavras:
        atual.append(p)
        if p["texto"][-1:] in ".?!" or len(atual) >= max_palavras:
            linhas.append(f"[{atual[0]['inicio']:.1f}] " + " ".join(x["texto"] for x in atual))
            atual = []
    if atual:
        linhas.append(f"[{atual[0]['inicio']:.1f}] " + " ".join(x["texto"] for x in atual))
    return "\n".join(linhas)


def janela_contexto(palavras, inicio, fim, antes=JANELA_ANTES_S, depois=JANELA_DEPOIS_S):
    return compactar_transcricao(
        [p for p in palavras if inicio - antes <= p["inicio"] <= fim + depois]
    )


def validar_receita(receita, momento, idioma):
    erros = []
    originais = [b for b in receita["blocos"] if b["tipo"] == "original"]
    narracoes = [b for b in receita["blocos"] if b["tipo"] == "narracao"]
    for b in originais:
        dur = b["fim"] - b["inicio"]
        if dur <= 0 or dur > MAX_ORIGINAL_S:
            erros.append(f"trecho original {b['inicio']:.1f}-{b['fim']:.1f} deve durar entre 0 e {MAX_ORIGINAL_S} s")
        if b["inicio"] < momento["inicio"] - FOLGA_MOMENTO_S or b["fim"] > momento["fim"] + FOLGA_MOMENTO_S:
            erros.append(f"trecho original {b['inicio']:.1f}-{b['fim']:.1f} está fora do momento escolhido")
    for b in narracoes:
        if not momento["inicio"] - JANELA_ANTES_S <= b["inicio"] <= momento["fim"] + JANELA_DEPOIS_S:
            erros.append(f"gameplay da narração em {b['inicio']:.1f}s está fora da janela do momento")
        if not b[idioma].strip():
            erros.append(f"[{idioma}] bloco de narração vazio")
    s_narr = sum(len(b[idioma].split()) for b in narracoes) / IDIOMAS[idioma]["pps"]
    s_orig = sum(b["fim"] - b["inicio"] for b in originais)
    total = s_narr + s_orig
    if total and s_narr / total < MIN_NARRACAO:
        erros.append(f"[{idioma}] narração estimada em {s_narr / total:.0%}; precisa ser pelo menos 40% do tempo")
    if not DURACAO_MIN_S <= total <= DURACAO_MAX_S:
        erros.append(f"[{idioma}] duração estimada {total:.0f} s; precisa ficar entre 61 e 90 s")
    return erros


def validar_idiomas(receita, momento):
    return {idioma: validar_receita(receita, momento, idioma) for idioma in IDIOMAS}


def status(receita):
    if not receita["fiel_ao_contexto"] or receita["score"] < 60:
        return "descartado"
    return "revisar" if receita["score"] < 85 else "pronto"


PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
TEMAS = ["easter_egg", "unlockable", "guide", "retrospective"]

MOMENTOS_SCHEMA = {
    "type": "object",
    "properties": {"momentos": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "inicio": {"type": "number"},
            "fim": {"type": "number"},
            "tema": {"type": "string", "enum": TEMAS},
            "motivo": {"type": "string"},
            "score_viral": {"type": "integer"},
        },
        "required": ["inicio", "fim", "tema", "motivo", "score_viral"],
        "additionalProperties": False,
    }}},
    "required": ["momentos"],
    "additionalProperties": False,
}

META_SCHEMA = {
    "type": "object",
    "properties": {
        "titulo": {"type": "string"},
        "tiktok_legenda": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "produto": {"type": "string"},
    },
    "required": ["titulo", "tiktok_legenda", "hashtags", "produto"],
    "additionalProperties": False,
}

RECEITA_SCHEMA = {
    "type": "object",
    "properties": {
        "tema": {"type": "string", "enum": TEMAS},
        "blocos": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "tipo": {"type": "string", "enum": ["narracao", "original"]},
                "en": {"type": "string"},
                "pt": {"type": "string"},
                "inicio": {"type": "number"},
                "fim": {"type": "number"},
                "legenda_en": {"type": "string"},
                "legenda_pt": {"type": "string"},
            },
            "required": ["tipo", "en", "pt", "inicio", "fim", "legenda_en", "legenda_pt"],
            "additionalProperties": False,
        }},
        "en": META_SCHEMA,
        "pt": META_SCHEMA,
        "score": {"type": "integer"},
        "fiel_ao_contexto": {"type": "boolean"},
        "alertas": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["tema", "blocos", "en", "pt", "score", "fiel_ao_contexto", "alertas"],
    "additionalProperties": False,
}


def _chamar(cliente, prompt, usuario, schema):
    resp = cliente.beta.messages.create(
        model=os.environ.get("CLAUDE_MODEL") or "claude-opus-5-5",
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": schema}},
        system=(PROMPTS / prompt).read_text("utf-8"),
        messages=[{"role": "user", "content": usuario}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude recusou a solicitação")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("resposta do Claude cortada (max_tokens)")
    return json.loads(next(b.text for b in resp.content if b.type == "text"))


def achar_momentos(cliente, palavras, n=5):
    dados = _chamar(cliente, "momentos.md", compactar_transcricao(palavras), MOMENTOS_SCHEMA)
    return sorted(dados["momentos"], key=lambda m: m["score_viral"], reverse=True)[:n]


def roteirizar(cliente, palavras, momento, criador):
    usuario = (
        f"Criador do vídeo original: {criador}\n"
        f"Momento escolhido: {momento['inicio']:.1f}s a {momento['fim']:.1f}s "
        f"(tema: {momento['tema']}; motivo: {momento['motivo']})\n\n"
        f"Transcrição com contexto:\n"
        f"{janela_contexto(palavras, momento['inicio'], momento['fim'])}"
    )
    receita = _chamar(cliente, "roteiro.md", usuario, RECEITA_SCHEMA)
    erros = validar_idiomas(receita, momento)
    if all(erros.values()):
        todos = sorted({e for lista in erros.values() for e in lista})
        usuario += "\n\nSua resposta anterior violou estas regras; corrija:\n- " + "\n- ".join(todos)
        receita = _chamar(cliente, "roteiro.md", usuario, RECEITA_SCHEMA)
        erros = validar_idiomas(receita, momento)
    return receita, erros

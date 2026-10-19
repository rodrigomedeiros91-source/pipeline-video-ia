"""Valida o roteiro JSON do canal de história (contrato da parte 1 com as partes 2–4)."""
import json
import re
import sys
from pathlib import Path

POSES = {"neutro", "apontando", "explicando", "chocado", "rindo", "pensando", "facepalm",
         "cetico", "comemorando", "assustado", "confuso", "entediado", "irritado",
         "cochichando", "lendo", "dando_de_ombros",
         # extras com objetos
         "lupa", "luneta", "globo", "mapa", "livros", "cafe", "notebook",
         "placa_interrogacao", "ideia", "sentado_pedra", "deitado", "caminhando", "bandeira",
         "oculos_escuros"}
TIPOS = {"acervo": "busca", "mapa": "busca", "texto": "texto_tela",
         "linha_tempo": "texto_tela", "cena": "cena"}
CAMPOS_TOPO = ["slug", "titulo", "descricao_youtube", "tags", "intro", "capitulos", "outro",
               "alertas"]
CAMPOS_VISUAL = ["tipo", "busca", "cena", "texto_tela", "mascote"]
PALAVRAS_TRECHO = (10, 40)
# Limites de palavras (capítulo, intro) por "formato" do roteiro. O 2 (feedback de 2026-10-06) tem mitos
# de ~70–93 s e intro = cold open de até ~20 s; roteiros sem o campo são do formato 1.
# O 3 (série em Partes, 2026-10-18) faz de cada capítulo uma Parte inteira que cabe num Short de 60 s.
LIMITES = {1: ((280, 380), (85, 130)), 2: ((200, 270), (25, 60)), 3: ((95, 120), (25, 60))}
FORMATO_ATUAL = 2
PALAVRAS_OUTRO = (40, 70)
CAPITULOS = (6, 8)
CENAS_POR_CAPITULO = (1, 3)
HASHTAGS = (2, 5)
FALA_SHORT = 20  # palavras da abertura e da pergunta faladas no Short (~3 s cada)


def _contar(texto):
    return sum(1 for w in texto.split() if any(c.isalnum() for c in w))


def _palavras(trechos):
    total = 0
    for t in trechos:
        narracao = t.get("narracao", "")
        if narracao is None:
            narracao = ""
        total += _contar(narracao)
    return total


def _validar_trecho(t, onde):
    erros = []
    n = _contar(t.get("narracao", ""))
    if not PALAVRAS_TRECHO[0] <= n <= PALAVRAS_TRECHO[1]:
        erros.append(f"{onde}: narração com {n} palavras ({PALAVRAS_TRECHO[0]}–{PALAVRAS_TRECHO[1]})")
    v = t.get("visual", {})
    faltando = [c for c in CAMPOS_VISUAL if c not in v]
    if faltando:
        return erros + [f"{onde}: visual sem {', '.join(faltando)}"]
    tipo = v["tipo"]
    if tipo not in TIPOS:
        return erros + [f"{onde}: tipo de visual inválido '{tipo}'"]
    if not v[TIPOS[tipo]].strip():
        erros.append(f"{onde}: visual '{tipo}' exige '{TIPOS[tipo]}'")
    if tipo == "texto" and "→" in v["texto_tela"]:  # a Patrick Hand não tem a seta: a lousa mostra um buraco
        erros.append(f"{onde}: texto_tela com '→' (use '—'; a seta só vale em linha_tempo)")
    if tipo == "cena" and v["mascote"]:
        erros.append(f"{onde}: cena não leva mascote")
    elif v["mascote"] and v["mascote"] not in POSES:
        erros.append(f"{onde}: pose desconhecida '{v['mascote']}'")
    return erros


def _validar_capitulo(cap, onde, palavras_capitulo):
    erros = []
    if not cap.get("titulo", "").strip():
        erros.append(f"{onde}: sem título")
    trechos = cap.get("trechos", [])
    n = _palavras(trechos)
    if not palavras_capitulo[0] <= n <= palavras_capitulo[1]:
        erros.append(f"{onde}: {n} palavras ({palavras_capitulo[0]}–{palavras_capitulo[1]})")
    for i, t in enumerate(trechos, 1):
        try:
            erros += _validar_trecho(t, f"{onde} trecho {i}")
        except (TypeError, AttributeError, KeyError) as e:
            erros.append(f"{onde} trecho {i}: formato inválido ({e})")
    cenas = sum(1 for t in trechos if t.get("visual", {}).get("tipo") == "cena")
    if not CENAS_POR_CAPITULO[0] <= cenas <= CENAS_POR_CAPITULO[1]:
        erros.append(f"{onde}: {cenas} cenas ({CENAS_POR_CAPITULO[0]}–{CENAS_POR_CAPITULO[1]})")
    fontes = cap.get("fontes", [])
    if not fontes:
        erros.append(f"{onde}: precisa de pelo menos 1 fonte")
    elif any(not f.get("url", "").startswith("http") for f in fontes):
        erros.append(f"{onde}: fonte sem url http")
    short = cap.get("short", {})
    titulo = short.get("titulo", "")
    if len(titulo) > 100 or not titulo.endswith("#Shorts"):
        erros.append(f"{onde}: título do Short deve ter até 100 caracteres e terminar com #Shorts")
    tags = short.get("hashtags", [])
    if not HASHTAGS[0] <= len(tags) <= HASHTAGS[1] or not all(isinstance(h, str) and re.fullmatch(r"#\w+", h) for h in tags):
        erros.append(f"{onde}: hashtags do Short devem ser {HASHTAGS[0]}–{HASHTAGS[1]} no formato #palavra")
    escolha = short.get("trechos")
    if escolha is not None and not (isinstance(escolha, list) and escolha and escolha == sorted(set(escolha))
                                    and all(isinstance(k, int) and 1 <= k <= len(trechos) for k in escolha)):
        erros.append(f"{onde}: short.trechos deve listar números de trecho (1–{len(trechos)}) em ordem, sem repetir")
    for campo in ("abertura", "pergunta"):
        if campo in short and not (isinstance(short[campo], str) and 1 <= len(short[campo].split()) <= FALA_SHORT):
            erros.append(f"{onde}: short.{campo} deve ter 1–{FALA_SHORT} palavras")
    return erros


def _validar_topo(dados):
    erros = []
    slug = dados["slug"]
    if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
        erros.append(f"slug inválido '{slug}' (use kebab-case)")
    titulo = dados["titulo"]
    if not isinstance(titulo, str) or not 1 <= len(titulo.strip()) <= 100:
        erros.append("titulo deve ter 1–100 caracteres")
    desc = dados["descricao_youtube"]
    if not isinstance(desc, str) or not desc.strip():
        erros.append("descricao_youtube vazia")
    tags = dados["tags"]
    if not isinstance(tags, list) or not tags or not all(isinstance(t, str) for t in tags):
        erros.append("tags deve ser lista não vazia de textos")
    if not isinstance(dados["alertas"], list):
        erros.append("alertas deve ser lista")
    return erros


def validar_roteiro(dados):
    if not isinstance(dados, dict):
        return ["roteiro deve ser um objeto JSON"]
    faltando = [c for c in CAMPOS_TOPO if c not in dados]
    if faltando:
        return [f"faltam campos: {', '.join(faltando)}"]
    erros = _validar_topo(dados)
    formato = dados.get("formato", 1)
    if formato not in LIMITES:
        return erros + [f"formato {formato!r} desconhecido (use {', '.join(map(str, LIMITES))})"]
    palavras_capitulo, palavras_intro = LIMITES[formato]
    for nome, (minimo, maximo) in (("intro", palavras_intro), ("outro", PALAVRAS_OUTRO)):
        try:
            n = _palavras(dados[nome])
            if not minimo <= n <= maximo:
                erros.append(f"{nome}: {n} palavras ({minimo}–{maximo})")
            for i, t in enumerate(dados[nome], 1):
                try:
                    erros += _validar_trecho(t, f"{nome} trecho {i}")
                except (TypeError, AttributeError, KeyError) as e:
                    erros.append(f"{nome} trecho {i}: formato inválido ({e})")
        except (TypeError, AttributeError, KeyError) as e:
            erros.append(f"{nome}: formato inválido ({e})")
    caps = []
    try:
        caps = dados["capitulos"]
        if not CAPITULOS[0] <= len(caps) <= CAPITULOS[1]:
            erros.append(f"{len(caps)} capítulos ({CAPITULOS[0]}–{CAPITULOS[1]})")
    except (TypeError, AttributeError, KeyError) as e:
        erros.append(f"capitulos: formato inválido ({e})")
    for i, cap in enumerate(caps, 1):
        try:
            erros += _validar_capitulo(cap, f"capítulo {i}", palavras_capitulo)
        except (TypeError, AttributeError, KeyError) as e:
            erros.append(f"capítulo {i}: formato inválido ({e})")
    return erros


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("uso: python -m fabrica.roteiro <arquivo.json>")
        return 2
    try:
        dados = json.loads(Path(args[0]).read_text("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        print(f"erro ao ler {args[0]}: {e}")
        return 2
    erros = validar_roteiro(dados)
    stem = Path(args[0]).stem
    if isinstance(dados, dict) and "slug" in dados and dados["slug"] != stem:
        erros.append(f"slug '{dados['slug']}' diferente do nome do arquivo '{stem}'")
    print("\n".join(erros) if erros else "OK")
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())

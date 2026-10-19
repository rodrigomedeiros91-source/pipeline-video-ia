"""Saídas de texto do vídeo longo: legendas .srt e descrição do YouTube."""

MAX_CHARS = 42
MAX_LINHAS = 2
MAX_SEG = 6.0
LIMITE_DESCRICAO = 5000


def tempo_srt(s: float) -> str:
    ms = round(s * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    seg, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{seg:02d},{ms:03d}"


def tempo_capitulo(s: float) -> str:
    h, resto = divmod(int(s), 3600)
    m, seg = divmod(resto, 60)
    return f"{h}:{m:02d}:{seg:02d}" if h else f"{m}:{seg:02d}"


def _linhas(textos):
    linhas = []
    for t in textos:
        if linhas and len(linhas[-1]) + 1 + len(t) <= MAX_CHARS:
            linhas[-1] += f" {t}"
        else:
            linhas.append(t)
    return linhas


def legendas(palavras) -> str:
    """Legendas de até 2 linhas × 42 caracteres e 6 s, quebrando de preferência no fim de frase."""
    grupos, atual = [], []
    for p in palavras:
        if atual and (len(_linhas([x["texto"] for x in atual + [p]])) > MAX_LINHAS
                      or p["fim"] - atual[0]["inicio"] > MAX_SEG):
            grupos.append(atual)
            atual = []
        atual.append(p)
        if p["texto"].rstrip('"\'”’)').endswith((".", "?", "!")):
            grupos.append(atual)
            atual = []
    if atual:
        grupos.append(atual)
    return "\n".join(
        f"{i}\n{tempo_srt(g[0]['inicio'])} --> {tempo_srt(g[-1]['fim'])}\n"
        f"{chr(10).join(_linhas([x['texto'] for x in g]))}\n"
        for i, g in enumerate(grupos, 1))


def creditos_obrigatorios(creditos: str) -> str:
    """Só as linhas que exigem atribuição (CC BY/BY-SA); domínio público e CC0 viram uma linha."""
    linhas = creditos.strip().split(chr(10))
    itens = [l for l in linhas if l.startswith("- ")]
    exigem = [l for l in itens if "CC BY" in l]
    outras = [l for l in linhas if not l.startswith("- ")]
    saida = [outras[0], *exigem]
    if len(exigem) < len(itens):
        saida.append("- Other images: public domain / CC0, via Wikimedia Commons.")
    return chr(10).join(saida + outras[1:])


def descricao(roteiro, capitulos, creditos: str) -> str:
    linhas = [f"TITLE: {roteiro['titulo']}", "", roteiro["descricao_youtube"].strip(), "",
              "Chapters:"]
    for c in capitulos:
        nome = c["titulo"] if c["id"] in ("intro", "outro") else f"#{c['id']} {c['titulo']}"
        linhas.append(f"{tempo_capitulo(c['inicio'])} {nome}")
    urls = dict.fromkeys(f["url"] for cap in roteiro["capitulos"] for f in cap["fontes"])
    linhas += ["", "Sources:", *(f"- {u}" for u in urls), "", creditos_obrigatorios(creditos), "",
               "TAGS: " + ", ".join(roteiro["tags"])]
    return "\n".join(linhas) + "\n"

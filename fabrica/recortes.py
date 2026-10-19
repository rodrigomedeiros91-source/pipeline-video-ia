"""Formato "recortes" (2026-10-18, dinâmica da referência Null History): cada frase da narração ganha uma
ilustração stick figure em tela cheia (~3 s), com a frase escrita na tela; sem cartão, lousa nem acervo.
O longo do YouTube é horizontal (16:9); as Partes (cortes para Reels/Shorts) são verticais e a câmera
desliza pela mesma ilustração. Reaproveita a narração em cache da montagem.

Uso: python -m fabrica.recortes <slug> [--musica NOME] [--so-partes 1 2] [--sem-longo]
Cenas em historia/recortes/<slug>.json: {"titulo_tela": "...", "blocos": {"intro": [{"frase", "cena"}], "1": [...]}}
"""
import argparse
import base64
import json
import mimetypes
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from fabrica import clipes, montagem, saidas, salvar_json, shorts
from fabrica.render import tempo_ass

BASE = montagem.BASE
HORIZ, VERT = (1920, 1080), (1080, 1920)
FIM_PARTE = 1.0    # respiro depois do gancho da Parte
LIMITE_PARTE = 89.5  # com as pausas a Parte passa de 60 s; o Business Suite agenda Reels até 90 s
FOLGA_MIN = 0.2     # silêncio mínimo do narrador para cortar o áudio ali sem comer palavra
PAUSA = 0.8         # respiro no fim de cada sentença: as cenas ficam mais tempo na tela (pedido de 2026-10-18)
PAN_VERTICAL = (0.25, 0.75)  # trecho da largura que a janela vertical percorre em cada frase
MODELO, TAMANHO, QUALIDADE = "gpt-image-2", "1536x1024", "medium"
ESTILO = (
    "Wide 16:9 illustration for a history explainer video. Dense, richly detailed, highly saturated comic-book "
    "illustration with bold black outlines and flat vivid colors, dramatic skies (orange, gold, deep blue), "
    "crowds and depth; the action spread across the width, foreground characters large at the bottom edge. "
    "Every person is a simple cartoon character with a plain round head (white or pale beige), tiny dot eyes "
    "and a small line mouth, no nose, simple thin limbs, wearing detailed period clothing, helmets, crowns or "
    "armor. No text, letters or captions in the image unless the scene explicitly asks for a word. ")
MASCOTE = ("The channel mascot troll appears in this scene: draw him exactly like the reference image (wild white "
           "hair, pointed ears, round nose, green suspenders), dressed for the period if the scene says so. ")
SEM_MASCOTE = "No troll or mascot character in this scene. "
CREDITOS = "Illustrations: generated with AI (OpenAI) in the channel's stick-figure style."
mimetypes.add_type("image/webp", ".webp")

ESTILOS_ASS = {  # (tamanho da frase, altura da frase, tamanho do título, margem do título)
    HORIZ: (66, 800, 112, 150),
    VERT: (64, 1180, 104, 260),
}


def _palavras(texto):
    return texto.split()


def validar(roteiro, rec):
    """Erros: as frases de cada bloco precisam reproduzir a narração palavra por palavra (o tempo vem dela)."""
    erros = []
    blocos = rec.get("blocos", {})
    for b in montagem.blocos(roteiro):
        cenas = blocos.get(b["id"])
        if not cenas:
            erros.append(f"bloco {b['id']}: sem cenas")
            continue
        if _palavras(" ".join(c.get("frase", "") for c in cenas)) != _palavras(montagem.texto_do_bloco(b)):
            erros.append(f"bloco {b['id']}: as frases não reproduzem a narração palavra por palavra")
        erros += [f"bloco {b['id']} cena {k}: sem descrição" for k, c in enumerate(cenas, 1) if not c.get("cena", "").strip()]
    return erros


def ass(frases, tam=HORIZ, titulo=None):
    """Legenda: uma frase por vez na tela; título grande opcional ((texto, ini, fim))."""
    w, h = tam
    fs, y, ts, mt = ESTILOS_ASS[tam]
    cab = ("[Script Info]\nScriptType: v4.00+\n"
           f"PlayResX: {w}\nPlayResY: {h}\nWrapStyle: 0\n\n[V4+ Styles]\n"
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
           "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
           "MarginL, MarginR, MarginV, Encoding\n"
           f"Style: Frase,Arial,{fs},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,5,2,5,90,90,0,1\n"
           f"Style: Titulo,Arial Black,{ts},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,8,3,8,"
           f"60,60,{mt},1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    linhas = [f"Dialogue: 0,{tempo_ass(a)},{tempo_ass(z)},Frase,,0,0,0,,{{\\pos({w // 2},{y})}}"
              f"{t.replace('{', '(').replace('}', ')')}\n" for t, a, z in frases if t]
    if titulo:
        t, a, z = titulo
        linhas.append(f"Dialogue: 1,{tempo_ass(a)},{tempo_ass(z)},Titulo,,0,0,0,,{t.replace(chr(10), chr(92) + 'N')}\n")
    return cab + "".join(linhas)


def _tela(origem, destino):
    """Recorta a ilustração 3:2 para 16:9 (cobre a tela sem distorcer)."""
    im = Image.open(origem).convert("RGB")
    w, h = im.size
    nh = round(w * HORIZ[1] / HORIZ[0])
    im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh)).resize(HORIZ, Image.LANCZOS).save(destino)


def imagem(cliente, pasta, cena):
    """Ilustração 16:9 da cena (cache pelo texto da cena); com o mascote, a pose dele vai de referência."""
    nome = montagem._hash8(cena)
    final = pasta / f"{nome}-16x9.png"
    if final.exists():
        return final
    bruta = pasta / f"{nome}.png"
    if not bruta.exists():
        com_mascote = "troll" in cena.lower() or "mascot" in cena.lower()
        prompt = ESTILO + (MASCOTE if com_mascote else SEM_MASCOTE) + "Scene: " + cena
        if com_mascote:
            with open(BASE / "mascote" / "poses" / "neutro.webp", "rb") as ref:
                r = cliente.images.edit(model=MODELO, image=[ref], prompt=prompt, size=TAMANHO, quality=QUALIDADE)
        else:
            r = cliente.images.generate(model=MODELO, prompt=prompt, size=TAMANHO, quality=QUALIDADE)
        pasta.mkdir(parents=True, exist_ok=True)
        bruta.write_bytes(base64.b64decode(r.data[0].b64_json))
    _tela(bruta, final)
    return final


def folgas(palavras, frases):
    """Silêncio (s) entre o fim de cada frase e a palavra seguinte; a última frase tem folga infinita."""
    out, k = [], 0
    for f in frases[:-1]:
        k += len(f.split())
        out.append(palavras[k]["inicio"] - palavras[k - 1]["fim"])
    return out + [float("inf")]


def espacar(wav, tempos, frases, folga, pausa=PAUSA):
    """Narração com uma pausa no fim de cada sentença (e do bloco): segmentos de áudio, novos (ini, fim) de cada
    frase e duração. Só corta onde o narrador já respira (fim de sentença com folga >= FOLGA_MIN): cortar no meio
    da fala engasgava a voz (2026-10-18)."""
    segs, novos, t, ini = [], [], 0.0, 0.0
    for k, ((a, z), f, g) in enumerate(zip(tempos, frases, folga)):
        fecha = k == len(tempos) - 1 or (f.rstrip().rstrip("\"'”’)").endswith((".", "?", "!")) and g >= FOLGA_MIN)
        novos.append((t + a - ini, t + z - ini + (pausa if fecha else 0.0)))
        if fecha:
            segs += [(wav, ini, z), pausa]
            t += z - ini + pausa
            ini = z
    return segs, novos, t


def srt(frases):
    """Legendas do YouTube: uma frase por bloco, nos mesmos tempos da tela."""
    return "\n".join(f"{k}\n{saidas.tempo_srt(a)} --> {saidas.tempo_srt(z)}\n{t}\n"
                     for k, (t, a, z) in enumerate(frases, 1))


def eventos(segmentos):
    """segmentos = [(imagem, ini, fim, frase)] na linha do vídeo → eventos com quadros sem deriva."""
    out = []
    for k, (img, a, z, frase) in enumerate(segmentos):
        n = round(z * clipes.FPS) - round(a * clipes.FPS)
        out.append({"imagem": img, "quadros": n, "frase": frase, "pan": (0, 1, -1)[k % 3]})
    return out


def _clipe_vertical(img, n, sentido, destino):
    """A janela 9:16 desliza pela ilustração 16:9 (esquerda→direita ou o contrário)."""
    a, b = PAN_VERTICAL if sentido >= 0 else PAN_VERTICAL[::-1]
    x = f"(iw-{VERT[0]})*({a}+({b - a})*n/{max(n - 1, 1)})"
    clipes._gerar(["-loop", "1", "-framerate", str(clipes.FPS), "-i", str(img), "-vf",
                   f"scale=-2:{VERT[1]},crop={VERT[0]}:{VERT[1]}:x='{x}':y=0,format=yuv420p",
                   "-frames:v", str(n), *clipes.VIDEO], destino)


def render(evts, pasta, destino_mudo, tam=HORIZ):
    """Um clipe por imagem (horizontal: zoom lento; vertical: janela deslizando) e cortes secos."""
    lista = []
    for k, e in enumerate(evts):
        img = Path(e["imagem"])
        sentido = 1 if k % 2 else -1
        chave = montagem._hash8(f"{img.name}|{e['quadros']}|{e['pan']}|{sentido}|{tam}|v3")
        clipe = pasta / "clipes" / f"{img.stem}-{chave}.mp4"
        if not clipe.exists():
            if tam == VERT:
                _clipe_vertical(img, e["quadros"], sentido, clipe)
            else:
                clipes.render_clipe({"quadros": e["quadros"], "troll": None, "tamanho": tam, "fundo": str(img),
                                     "modo": "zoom", "pan": e["pan"]}, clipe)
        lista.append(clipe)
    clipes.concatenar(lista, destino_mudo)


def finalizar(segs_audio, evts, legenda, total, musicas, slug, pasta, destino, tam):
    """Narração + música, vídeo, legenda gravada; grava em destino."""
    pasta.mkdir(parents=True, exist_ok=True)
    clipes.faixa_narracao(segs_audio, pasta / "narracao.wav")
    faixas = clipes.playlist(musicas, slug, total, {m: clipes.duracao(m) for m in musicas})
    clipes.mixar(pasta / "narracao.wav", faixas, total, pasta / "mix.m4a")
    render(evts, pasta.parent, pasta / "mudo.mp4", tam)
    clipes.juntar(pasta / "mudo.mp4", pasta / "mix.m4a", pasta / "sem_legenda.mp4")
    (pasta / "legenda.ass").write_text(legenda, "utf-8")
    shorts.legendar(pasta / "sem_legenda.mp4", pasta / "legenda.ass", destino)


def _cliente_openai():
    from openai import OpenAI
    return OpenAI()


def main(argv=None, base=BASE, criar_cliente=montagem._cliente_elevenlabs, criar_openai=_cliente_openai):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m fabrica.recortes", description=__doc__.splitlines()[0])
    ap.add_argument("slug")
    ap.add_argument("--musica", default="", help="só usa músicas cujo nome contém este texto")
    ap.add_argument("--so-partes", type=int, nargs="*", default=None, help="gera só estas Partes")
    ap.add_argument("--sem-longo", action="store_true")
    args = ap.parse_args(argv)
    from dotenv import load_dotenv
    load_dotenv(base.parent / ".env")
    roteiro = json.loads((base / "roteiros" / f"{args.slug}.json").read_text("utf-8"))
    rec = json.loads((base / "recortes" / f"{args.slug}.json").read_text("utf-8"))
    erros = validar(roteiro, rec)
    if erros:
        print("\n".join(erros))
        return 2
    voz = os.environ.get("ELEVENLABS_VOZ_HISTORIA")
    musicas = [m for m in sorted((base / "musica").glob("*.mp3")) if args.musica.lower() in m.name.lower()]
    if not (voz and musicas):
        print("faltando ELEVENLABS_VOZ_HISTORIA no .env ou música em historia/musica/")
        return 2
    pasta = base / "recortes" / args.slug
    narracao = base / "montagem" / args.slug / "narracao"
    cli_voz, cli_img = [], []

    def voz_cliente():
        if not cli_voz:
            cli_voz.append(criar_cliente())
        return cli_voz[0]

    def img_cliente():
        if not cli_img:
            cli_img.append(criar_openai())
        return cli_img[0]

    bls = {b["id"]: b for b in montagem.blocos(roteiro)}
    falados = {}
    for bid, b in bls.items():
        wav, pal = montagem.narrar_bloco(voz_cliente, narracao, b, voz)
        cenas = rec["blocos"][bid]
        ts, prop = montagem.fronteiras(pal, [c["frase"] for c in cenas], clipes.duracao(wav))
        if prop:
            print(f"alerta: alinhamento do bloco {bid} não bate; divisão proporcional")
        frases = [c["frase"] for c in cenas]
        audio, ts, dur = espacar(wav, ts, frases, folgas(pal, frases) if not prop else [0.0] * len(frases))
        falados[bid] = {"audio": audio, "dur": dur, "cenas": cenas, "tempos": ts}

    caps = [b for b in bls if b not in ("intro", "outro")]
    partes = [n for n in range(1, len(caps) + 1) if not args.so_partes or n in args.so_partes]
    usados = list(bls) if not args.sem_longo else [caps[n - 1] for n in partes]
    so_capa = {caps[n] if n < len(caps) else "intro" for n in partes} - set(usados)  # 1ª cena da Parte seguinte
    pedidos = [(bid, c) for bid in [*usados, *so_capa] for c in (falados[bid]["cenas"][:1] if bid in so_capa
                                                                  else falados[bid]["cenas"])]
    print(f"ilustrações ({len(pedidos)})…", flush=True)
    img_cliente()  # cria o cliente antes das threads

    def uma(pedido):
        try:
            return imagem(cli_img[0], pasta / "img", pedido[1]["cena"])
        except Exception as e:  # OpenAI: crédito, moderação, rede
            return e

    with ThreadPoolExecutor(6) as ex:
        feitas = list(ex.map(uma, pedidos))
    for (bid, c), img in zip(pedidos, feitas):
        if isinstance(img, Exception):
            print(f"erro na ilustração '{c['frase']}': {img}")
            return 1
        falados[bid].setdefault("imagens", []).append(img)

    if not args.sem_longo:
        t, segs_a, segs_v, frases, capitulos = 0.0, [], [], [], []
        for bid in bls:
            f, inicio = falados[bid], t
            segs_a += f["audio"]
            for (a, z), img, c in zip(f["tempos"], f["imagens"], f["cenas"]):
                segs_v.append((img, t + a, t + z, c["frase"]))
                frases.append((c["frase"], t + a, t + z))
            capitulos.append({"id": bid, "titulo": bls[bid]["titulo"], "inicio": inicio, "inicio_narracao": t,
                              "fim": t + f["dur"], "short": bls[bid]["short"]})
            t += f["dur"]
        a, z = falados["intro"]["tempos"][0]
        titulo = (rec["titulo_tela"], a, z) if rec.get("titulo_tela") else None
        print(f"longo ({t / 60:.1f} min)…", flush=True)
        saida = base / "videos" / args.slug
        finalizar(segs_a, eventos(segs_v), ass(frases, HORIZ, titulo), t, musicas, args.slug, pasta / "longo",
                  saida / "video.mp4", HORIZ)
        salvar_json(saida / "capitulos.json", capitulos)
        (saida / "legendas.srt").write_text(srt(frases), "utf-8")
        (saida / "descricao.txt").write_text(saidas.descricao(roteiro, capitulos, CREDITOS), "utf-8")

    duracoes = []
    for n in partes:
        bid = caps[n - 1]
        short = bls[bid]["short"]
        ab, _ = shorts.narrar_fala(voz_cliente, narracao, f"short{n}-abertura", short["abertura"], voz)
        pg, _ = shorts.narrar_fala(voz_cliente, narracao, f"short{n}-pergunta", short["pergunta"], voz)
        f, dab, dpg = falados[bid], clipes.duracao(ab), clipes.duracao(pg)
        t = dab
        segs_v, frases = [], [(short["abertura"], 0.0, dab)]
        for k, ((a, z), img, c) in enumerate(zip(f["tempos"], f["imagens"], f["cenas"])):
            segs_v.append((img, 0.0 if k == 0 else t + a, t + z, c["frase"]))  # a abertura fala sobre a 1ª cena
            frases.append((c["frase"], t + a, t + z))
        t += f["dur"]
        prox = falados[caps[n]]["imagens"][0] if n < len(caps) else falados["intro"]["imagens"][0]
        segs_v.append((prox, t, t + dpg + FIM_PARTE, short["pergunta"]))  # a próxima Parte já aparece no gancho
        frases.append((short["pergunta"], t, t + dpg + FIM_PARTE))
        total = t + dpg + FIM_PARTE
        if total > LIMITE_PARTE:
            print(f"Parte {n}: {total:.0f} s passa de {LIMITE_PARTE:.0f} s; encurte a narração do capítulo")
            return 2
        print(f"Parte {n} ({total:.0f} s)…", flush=True)
        finalizar([ab, *f["audio"], pg, FIM_PARTE], eventos(segs_v), ass(frases, VERT), total, musicas, args.slug,
                  pasta / f"parte-{n}", base / "shorts" / args.slug / f"short-{n}.mp4", VERT)
        duracoes.append(round(total))
    print(f"pronto: longo={'não' if args.sem_longo else 'sim'}, Partes {duracoes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

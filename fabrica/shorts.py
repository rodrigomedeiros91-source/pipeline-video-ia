"""Shorts verticais do canal de história (YouTube Shorts, TikTok, Reels) e pacote de publicação."""
import argparse
import datetime as dt
import json
import math
import os
import sys

from fabrica import clipes, montagem, salvar_json, vertical
from fabrica.render import _ffmpeg, tempo_ass

BASE = montagem.BASE
FIM = 3.0
LIMITE = 59.5     # decisão de 2026-10-11 (Studio: Shorts curtos retêm mais; TikTok pausado): até 60 s
PLANO_MAX = 5.0   # visual parado não fica mais que isso sem trocar o movimento
MOVIMENTOS = (0, 1, -1)  # aproximação, panorâmica para a direita, para a esquerda
POSE_FIM = "apontando"
HORA_LONGO, HORA_SHORT, FUSO = "16:00", "13:00", "America/Sao_Paulo"
HORA_SHORT1 = "20:00"  # Short 1 sai no dia do longo, 4 h depois: no mesmo horário ele competia com o longo
EXTRAS_TIKTOK = ("#history", "#historytok", "#didyouknow")
EXTRAS_INSTAGRAM = ("#history", "#historyfacts", "#didyouknow")

CABECALHO_ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Legenda,Impact,88,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,7,0,2,60,60,330,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def eventos_short(trechos, dur, fim=FIM, divisiveis=()):
    """Trechos + cartão final (dur → dur+fim), com quadros sem deriva; devolve (eventos, duração total).
    Visual parado (id em divisiveis) com mais de PLANO_MAX s vira planos curtos alternando o movimento."""
    eventos = []
    for i, a, z in trechos:
        k = math.ceil((z - a) / PLANO_MAX - 1e-9) if i in divisiveis else 1
        passo = (z - a) / k
        eventos += [{"id": i if k == 1 else f"{i}-{j + 1}", "fonte": i, "ini": a + j * passo,
                     "fim": a + (j + 1) * passo, "pan": MOVIMENTOS[j % 3]} for j in range(k)]
    eventos.append({"id": "fim", "fonte": "fim", "ini": dur, "fim": dur + fim, "pan": 0})
    for e in eventos:
        e["quadros"] = round(e["fim"] * clipes.FPS) - round(e["ini"] * clipes.FPS)
    return eventos, dur + fim


def _desloca(palavras, d):
    return [{**p, "inicio": p["inicio"] + d, "fim": p["fim"] + d} for p in palavras]


def montar_short(todos, palavras, escolha, abertura=None, pergunta=None):
    """Linha do tempo do Short. todos = [(id, ini, fim)] dos trechos no WAV do capítulo; escolha = números
    dos trechos (None = todos); abertura/pergunta = (duração, palavras) das falas extras.
    Devolve áudio ("abertura", (ini, fim) no WAV, "pergunta"), visuais, palavras, fim dos trechos e do cartão."""
    trechos = [todos[k - 1] for k in escolha] if escolha else todos
    audio, visuais, pal, t = [], [], [], 0.0
    if abertura:
        audio.append("abertura")
        pal += abertura[1]
        t = abertura[0]
    for n, (i, a, z) in enumerate(trechos):
        audio.append((a, z))
        pal += _desloca([p for p in palavras if a <= p["inicio"] < z], t - a)
        visuais.append((i, 0.0 if n == 0 else t, t + z - a))
        t += z - a
    fim = FIM
    if pergunta:
        audio.append("pergunta")
        pal += _desloca(pergunta[1], t)
        fim += pergunta[0]
    if t + fim > LIMITE:
        raise ValueError(f"Short com {t + fim:.0f} s passa de 60 s: tire trechos em short.trechos")
    return {"audio": audio, "visuais": visuais, "palavras": pal, "fim_trechos": t, "fim": fim}


def blocos_legenda(palavras):
    """Blocos de até 3 palavras (fecham antes no fim de frase); pausas curtas emendam no próximo bloco."""
    grupos, atual = [], []
    for p in palavras:
        atual.append(p)
        if len(atual) == 3 or p["texto"].rstrip("\"'" + "”" + "’" + ")").endswith((".", "?", "!")):
            grupos.append(atual)
            atual = []
    if atual:
        grupos.append(atual)
    blocos = [{"texto": " ".join(p["texto"] for p in g).upper(), "inicio": g[0]["inicio"], "fim": g[-1]["fim"]}
              for g in grupos]
    for a, b in zip(blocos, blocos[1:]):
        if b["inicio"] - a["fim"] < 0.5:
            a["fim"] = b["inicio"]
    return blocos


def ass(blocos):
    linhas = (f"Dialogue: 0,{tempo_ass(b['inicio'])},{tempo_ass(b['fim'])},Legenda,,0,0,0,,"
              f"{b['texto'].replace('{', '(').replace('}', ')')}\n" for b in blocos)
    return CABECALHO_ASS + "".join(linhas)


def gancho(short):
    return short["titulo"].replace("#Shorts", "").strip()


def _tags(*grupos):
    """Hashtags na ordem, sem repetir."""
    return " ".join(dict.fromkeys(t for g in grupos for t in g))


def textos(short):
    """Textos por rede. A pergunta do Short vai na legenda do TikTok/Instagram: lá ela fica por cima do
    vídeo e faz o papel do comentário fixado (que nenhuma API deixa fixar)."""
    g, h = gancho(short), short["hashtags"]
    p = f"{short['pergunta']} 👇\n" if short.get("pergunta") else ""
    return {"descricao_youtube": f"{g}\n\nFull story: {{link_longo}}\n\n{_tags(h)}",
            "texto_tiktok": f"{g}{chr(10) + p if p else ' '}{_tags(h, EXTRAS_TIKTOK)}\nFull video on YouTube: The Myth Troll",
            "texto_instagram": f"{g}\n\n{p}Full video: link in bio\n\n{_tags(h, EXTRAS_INSTAGRAM)}"}


def proximo_sabado(hoje):
    return hoje + dt.timedelta(days=(5 - hoje.weekday()) % 7 or 7)


def datas(inicio, n):
    """[longo, short 1..n]: o Short 1 sai junto com o longo (dia D), os demais de D+1 a D+n-1."""
    return [inicio] + [inicio + dt.timedelta(days=k) for k in range(n)]


def _preservar(novo, antigo):
    """O que já saiu de 'pendente' mantém status, url e data/hora; a playlist sempre se mantém."""
    if not antigo:
        return
    for k in ("status", "url", "playlist"):
        if k in novo and antigo.get(k):
            novo[k] = antigo[k]
    if antigo.get("status", "pendente") != "pendente":
        novo["data"] = antigo.get("data", novo["data"])
        novo["hora"] = antigo.get("hora", novo["hora"])


def pacote(roteiro, slug, inicio, anterior=None, thumbnail_existe=True):
    dias = datas(inicio, len(roteiro["capitulos"]))
    longo = {"arquivo": f"historia/videos/{slug}/video.mp4", "titulo": roteiro["titulo"],
             "descricao": f"historia/videos/{slug}/descricao.txt",
             "legendas": f"historia/videos/{slug}/legendas.srt",
             "thumbnail": f"historia/canal/thumbs/{slug}.jpg" if thumbnail_existe else "",
             "data": dias[0].isoformat(), "hora": HORA_LONGO, "playlist": "", "status": "pendente", "url": ""}
    lista = [{"n": n, "arquivo": f"historia/shorts/{slug}/short-{n}.mp4", "titulo": cap["short"]["titulo"],
              **textos(cap["short"]), "data": dias[n].isoformat(), "hora": HORA_SHORT1 if n == 1 else HORA_SHORT,
              "status": "pendente", "url": ""}
             for n, cap in enumerate(roteiro["capitulos"], 1)]
    anterior = anterior or {}
    _preservar(longo, anterior.get("longo"))
    antigos = {s["n"]: s for s in anterior.get("shorts", [])}
    for s in lista:
        _preservar(s, antigos.get(s["n"]))
        if longo["url"]:
            s["descricao_youtube"] = s["descricao_youtube"].replace("{link_longo}", longo["url"])
    return {"slug": slug, "fuso": FUSO, "longo": longo, "shorts": lista}


def calendario_md(pac):
    longo = pac["longo"]
    linhas = [f"# Calendário — {pac['slug']}", "", f"Horários de Brasília ({pac['fuso']}).", ""]
    if not longo["thumbnail"]:
        linhas += [f"> Atenção: thumbnail ausente (historia/canal/thumbs/{pac['slug']}.jpg).", ""]
    linhas += ["| Data | Hora | O quê | Arquivo | Status |", "|---|---|---|---|---|",
               f"| {longo['data']} | {longo['hora']} | Vídeo longo | {longo['arquivo']} | {longo['status']} |"]
    linhas += [f"| {s['data']} | {s['hora']} | Short {s['n']}: {s['titulo']} | {s['arquivo']} | {s['status']} |"
               for s in pac["shorts"]]
    for s in pac["shorts"]:
        linhas += ["", f"## Short {s['n']} — {s['titulo']}", "", "**TikTok**", "```text", s["texto_tiktok"],
                   "```", "", "**Instagram**", "```text", s["texto_instagram"], "```"]
    return "\n".join(linhas) + "\n"


def receita(evento, info, base, pasta, topo):
    """Gera as camadas verticais do evento e devolve a receita para clipes.render_clipe."""
    perg, fonte = base / "estilo" / "pergaminho.png", base / "fontes" / montagem.FONTE
    lousa = base / "estilo" / "objetos" / "lousa.png"
    pasta.mkdir(parents=True, exist_ok=True)
    nome = pasta / evento["id"]
    r = {"quadros": evento["quadros"], "tamanho": (vertical.W, vertical.H), "topo": str(topo), "troll": None}
    if info.get("animacao"):
        vertical.fundo(perg).save(f"{nome}-fundo.png", compress_level=1)
        r |= {"modo": "video", "video": info["animacao"], "duracao": clipes.duracao(info["animacao"]),
              "fundo": f"{nome}-fundo.png", "y": vertical.CY}
    elif info["tipo"] == "cena":
        caminhos = []
        for k, quadro in enumerate(vertical.cena(perg, info["cena"]), 1):
            quadro.save(f"{nome}-q{k}.png", compress_level=1)
            caminhos.append(f"{nome}-q{k}.png")
        r |= {"modo": "cena", "cena": caminhos, "pan": 1 if sum(map(ord, evento["id"])) % 2 else -1}
    elif info["tipo"] == "linha_tempo":
        fundo, marcos = vertical.linha_tempo(perg, fonte, info["texto"], bool(info["pose"]))
        fundo.save(f"{nome}.png", compress_level=1)
        r |= {"modo": "marcos", "fundo": f"{nome}.png", "marcos": []}
        for k, marco in enumerate(marcos):
            marco.save(f"{nome}-m{k}.png", compress_level=1)
            r["marcos"].append(f"{nome}-m{k}.png")
    else:
        if info["tipo"] == "fim":
            img = vertical.cartao_final(perg, lousa, fonte, info.get("pergunta", ""))
        elif info["tipo"] == "texto":
            img = vertical.lousa(perg, lousa, fonte, info["texto"], bool(info["pose"]))
        else:
            img = vertical.foto(perg, info["imagem"])
        img.resize((2 * vertical.W, 2 * vertical.H)).save(f"{nome}.png", compress_level=1)
        r |= {"modo": "zoom", "fundo": f"{nome}.png", "pan": evento.get("pan", 0)}
    if info["pose"]:
        troll, (x, y) = vertical.troll(base / "mascote" / "poses" / f"{info['pose']}.webp")
        troll.save(f"{nome}-troll.png", compress_level=1)
        r["troll"] = {"arquivo": f"{nome}-troll.png", "x": x, "y": y}
    return r


def render_evento(evento, info, base, pasta, topo, texto_gancho):
    origens = [montagem._origem(p) for p in [info.get("imagem"), info.get("animacao"), *info.get("cena", [])] if p]
    if info["pose"]:
        origens.append(montagem._origem(base / "mascote" / "poses" / f"{info['pose']}.webp"))
    chave = json.dumps({"versao": 3, "quadros": evento["quadros"], "pan": evento.get("pan", 0), "origens": origens,
                        "gancho": texto_gancho, **info}, sort_keys=True, ensure_ascii=False)
    destino = pasta / "clipes" / f"{evento['id']}-{montagem._hash8(chave)}.mp4"
    if not destino.exists():
        clipes.render_clipe(receita(evento, info, base, pasta / "camadas", topo), destino)
    return destino


def legendar(video, legenda, destino):
    """Grava a legenda ASS na imagem (cwd na pasta da legenda: evita escapar C:\\ no filtro)."""
    tmp = destino.with_name(f"{destino.stem}.tmp{destino.suffix}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg(["-i", str(video.resolve()), "-vf", f"subtitles={legenda.name}", *clipes.VIDEO, "-c:a", "copy",
             "-movflags", "+faststart", str(tmp.resolve())], cwd=legenda.parent)
    os.replace(tmp, destino)


def narrar_fala(obter_cliente, pasta, nome, texto, voz):
    """Fala extra do Short (abertura ou pergunta), com o mesmo cache de narração do vídeo longo."""
    return montagem.narrar_bloco(obter_cliente, pasta, {"id": nome, "trechos": [(nome, {"narracao": texto})]}, voz)


def fazer_short(n, bloco, wav, palavras, inf, base, pasta, musicas, slug, falas=None, gatilho=True):
    """Um Short do capítulo n: trechos escolhidos + falas extras, clipes verticais com cartão final,
    música e legenda gravada. falas = {"abertura"/"pergunta": (wav, palavras)} já narradas."""
    falas = falas or {}
    short = bloco["short"]
    cache = pasta / "cache" / str(n)
    cache.mkdir(parents=True, exist_ok=True)
    texto_gancho = gancho(short)
    topo = cache / "gancho.png"
    vertical.gancho(base / "fontes" / montagem.FONTE, texto_gancho).save(topo)
    cortes, _ = montagem.fronteiras(palavras, [t["narracao"] for _, t in bloco["trechos"]], clipes.duracao(wav))
    todos = [(i, a, z) for (i, _), (a, z) in zip(bloco["trechos"], cortes)]
    extra = {k: (clipes.duracao(w), pal) for k, (w, pal) in falas.items()}
    m = montar_short(todos, palavras, short.get("trechos"), extra.get("abertura"), extra.get("pergunta"))
    abertura = base / "visual" / slug / "imagens" / "intro.1-anim.mp4"  # a abertura animada do longo vira o gatilho
    if gatilho and abertura.exists() and m["visuais"]:  # na série (formato 3) cada Parte abre com a própria cena
        primeiro = m["visuais"][0][0]
        inf = {**inf, primeiro: {**inf[primeiro], "tipo": "cena", "animacao": str(abertura), "pose": ""}}
    parados = {i for i, _, _ in m["visuais"] if inf[i]["tipo"] not in ("cena", "linha_tempo")}
    eventos, total = eventos_short(m["visuais"], m["fim_trechos"], m["fim"], parados)
    info_fim = {"tipo": "fim", "pose": POSE_FIM, "pergunta": short.get("pergunta", "")}
    lista = [render_evento(e, info_fim if e["fonte"] == "fim" else inf[e["fonte"]], base, cache, topo, texto_gancho)
             for e in eventos]
    audio = [falas[a][0] if isinstance(a, str) else (wav, *a) for a in m["audio"]]
    clipes.faixa_narracao([*audio, FIM], cache / "narracao.wav")
    faixas = clipes.playlist(musicas, f"{slug}-{n}", total, {m: clipes.duracao(m) for m in musicas})
    clipes.mixar(cache / "narracao.wav", faixas, total, cache / "mix.m4a")
    clipes.concatenar(lista, cache / "video_sem_audio.mp4")
    clipes.juntar(cache / "video_sem_audio.mp4", cache / "mix.m4a", cache / "sem_legenda.mp4")
    (cache / "legenda.ass").write_text(ass(blocos_legenda(m["palavras"])), "utf-8")
    legendar(cache / "sem_legenda.mp4", cache / "legenda.ass", pasta / f"short-{n}.mp4")
    return total


def main(argv=None, base=BASE, hoje=None, criar_cliente=montagem._cliente_elevenlabs):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m fabrica.shorts",
                                 description="Shorts verticais de cada capítulo + pacote de publicação")
    ap.add_argument("slug")
    ap.add_argument("--inicio", default="", help="dia do vídeo longo (AAAA-MM-DD); padrão: próximo sábado")
    ap.add_argument("--musica", default="", help="só usa músicas cujo nome contém este texto")
    ap.add_argument("--so", type=int, nargs="+", default=[], metavar="N",
                    help="refaz só estes Shorts (ex.: --so 2); os outros ficam como estão")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0

    erros, roteiro, manifesto = montagem.checar(base, args.slug)
    if erros:
        print("\n".join(erros))
        return 2
    try:
        inicio = dt.date.fromisoformat(args.inicio) if args.inicio else proximo_sabado(hoje or dt.date.today())
    except ValueError:
        print(f"--inicio inválido: '{args.inicio}' (use AAAA-MM-DD)")
        return 2
    voz = os.environ.get("ELEVENLABS_VOZ_HISTORIA")
    if not voz:
        print("Faltando ELEVENLABS_VOZ_HISTORIA no .env.")
        return 2
    musicas = [m for m in sorted((base / "musica").glob("*.mp3")) if args.musica.lower() in m.name.lower()]
    if not musicas:
        print(f"nenhuma música em historia/musica/ contém '{args.musica}'")
        return 2
    longo = base / "videos" / args.slug
    if not ((longo / "video.mp4").exists() and (longo / "capitulos.json").exists()):
        print(f"vídeo longo ausente: rode python -m fabrica.montagem {args.slug} antes")
        return 2
    capitulos = montagem.blocos(roteiro)[1:-1]
    narracao = base / "montagem" / args.slug / "narracao"
    arquivos = [montagem.arquivos_narracao(narracao, b, voz) for b in capitulos]
    if not all(js.exists() and wav.exists() for _, js, wav in arquivos):
        print(f"narração em cache ausente: rode python -m fabrica.montagem {args.slug} antes")
        return 2

    inf = montagem.infos(roteiro, manifesto, base, args.slug)
    pasta = base / "shorts" / args.slug
    cliente = []

    def obter_cliente():
        if not cliente:
            cliente.append(criar_cliente())
        return cliente[0]

    duracoes = []
    for n, (bloco, (_, js, wav)) in enumerate(zip(capitulos, arquivos), 1):
        if args.so and n not in args.so:
            continue
        print(f"  Short {n}/{len(capitulos)}", flush=True)
        try:
            falas = {k: narrar_fala(obter_cliente, narracao, f"short{n}-{k}", bloco["short"][k], voz)
                     for k in ("abertura", "pergunta") if bloco["short"].get(k)}
        except Exception as err:  # ElevenLabs (cota, rede, chave) ou FFmpeg no WAV
            print(f"erro ao narrar as falas do Short {n}: {err}")
            return 1
        try:
            duracoes.append(fazer_short(n, bloco, wav, json.loads(js.read_text("utf-8")), inf, base, pasta,
                                        musicas, args.slug, falas, gatilho=roteiro.get("formato") != 3))
        except ValueError as err:
            print(f"Short {n}: {err}")
            return 2
        except RuntimeError as err:
            print(f"erro no FFmpeg no Short {n}: {err}")
            return 1
        except PermissionError:
            print(f"short-{n}.mp4 está aberto em outro programa (player?): feche e rode de novo")
            return 1

    arq = pasta / "publicacao.json"
    anterior = json.loads(arq.read_text("utf-8")) if arq.exists() else None
    pac = pacote(roteiro, args.slug, inicio, anterior,
                 thumbnail_existe=(base / "canal" / "thumbs" / f"{args.slug}.jpg").exists())
    salvar_json(arq, pac)
    (pasta / "calendario.md").write_text(calendario_md(pac), "utf-8")
    print(f"{len(duracoes)} Shorts ({', '.join(f'{d:.0f} s' for d in duracoes)}) → {pasta}")
    return 0


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    sys.exit(main())

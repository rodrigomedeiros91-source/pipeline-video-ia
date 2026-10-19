"""Montagem do vídeo longo do canal de história: narração, linha do tempo, clipes e saídas."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from fabrica import audio, camadas, clipes, saidas, salvar_json
from fabrica.roteiro import validar_roteiro

BASE = Path(__file__).resolve().parent.parent / "historia"
FONTE = "PatrickHand-Regular.ttf"
POSE_CARTAO = "apontando"
CARTAO = 2.0
MODELO_VOZ = "eleven_v4"
OBJETOS = ("lousa.png", "pergaminho.png")


def _hash8(texto):
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:8]


def blocos(roteiro):
    """Blocos de narração na ordem do vídeo: intro, capítulos 1..N, outro."""
    bls = [{"id": "intro", "titulo": "Intro", "short": None,
            "trechos": [(f"intro.{i}", t) for i, t in enumerate(roteiro["intro"], 1)]}]
    for c, cap in enumerate(roteiro["capitulos"], 1):
        bls.append({"id": str(c), "titulo": cap["titulo"], "short": cap["short"],
                    "trechos": [(f"{c}.{i}", t) for i, t in enumerate(cap["trechos"], 1)]})
    bls.append({"id": "outro", "titulo": "Outro", "short": None,
                "trechos": [(f"outro.{i}", t) for i, t in enumerate(roteiro["outro"], 1)]})
    return bls


def texto_do_bloco(bloco):
    return " ".join(t["narracao"] for _, t in bloco["trechos"])


def fronteiras(palavras, textos, dur):
    """[(ini, fim)] de cada trecho dentro do bloco e se precisou da divisão proporcional."""
    contagens = [len(t.split()) for t in textos]
    if len(palavras) == sum(contagens):
        cortes, k = [0.0], 0
        for n in contagens[:-1]:
            k += n
            cortes.append((palavras[k - 1]["fim"] + palavras[k]["inicio"]) / 2)
        cortes.append(dur)
        return list(zip(cortes, cortes[1:])), False
    total, acumulado, cortes = sum(len(t) for t in textos), 0, [0.0]
    for t in textos:
        acumulado += len(t)
        cortes.append(dur * acumulado / total)
    return list(zip(cortes, cortes[1:])), True


def linha_do_tempo(narrados):
    """Eventos (cartões e trechos) na linha global, com quadros sem deriva; capítulos; duração total."""
    t, eventos, capitulos = 0.0, [], []
    for b in narrados:
        inicio = t
        if b["id"] not in ("intro", "outro"):
            eventos.append({"id": f"cartao.{b['id']}", "ini": t, "fim": t + CARTAO})
            t += CARTAO
        eventos += [{"id": i, "ini": t + a, "fim": t + z} for i, a, z in b["trechos"]]
        capitulos.append({"id": b["id"], "titulo": b["titulo"], "inicio": inicio,
                          "inicio_narracao": t, "fim": t + b["dur"], "short": b["short"]})
        t += b["dur"]
    for e in eventos:
        e["quadros"] = round(e["fim"] * clipes.FPS) - round(e["ini"] * clipes.FPS)
    return eventos, capitulos, t


def arquivos_narracao(pasta, bloco, voz):
    h = _hash8(f"{texto_do_bloco(bloco)}|{voz}|{MODELO_VOZ}")
    mp3 = pasta / f"{bloco['id']}-{h}.mp3"
    return mp3, mp3.with_suffix(".json"), mp3.with_suffix(".wav")


def narrar_bloco(obter_cliente, pasta, bloco, voz):
    """WAV e palavras do bloco; só chama o ElevenLabs se não estiver em cache."""
    mp3, js, wav = arquivos_narracao(pasta, bloco, voz)
    if not (mp3.exists() and js.exists()):
        wav.unlink(missing_ok=True)
        palavras = audio.narrar(obter_cliente(), texto_do_bloco(bloco), mp3, voz, "en")
        salvar_json(js, palavras)
    if not wav.exists():
        clipes.para_wav(mp3, wav)
    return wav, json.loads(js.read_text("utf-8"))


def _arquivos_usados(entrada):
    arquivos = [o["arquivo"] for o in entrada.get("opcoes", []) if o["letra"] == entrada.get("escolhida")]
    arquivos += entrada.get("quadros", [])
    if entrada.get("mascote_arquivo"):
        arquivos.append(entrada["mascote_arquivo"])
    return arquivos


def checar(base, slug):
    """Erros de pré-condição (lista vazia = pode seguir), roteiro e manifesto. Nada aqui custa dinheiro."""
    try:
        roteiro = json.loads((base / "roteiros" / f"{slug}.json").read_text("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        return [f"erro ao ler o roteiro: {e}"], None, None
    erros = validar_roteiro(roteiro)
    if erros:
        return ["roteiro inválido (rode python -m fabrica.roteiro):", *erros], None, None
    if roteiro["slug"] != slug:
        return [f"slug '{roteiro['slug']}' diferente do nome do arquivo '{slug}'"], None, None
    visual = base / "visual" / slug
    try:
        manifesto = json.loads((visual / "manifesto.json").read_text("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        return [f"erro ao ler o manifesto (rode python -m fabrica.visual {slug}): {e}"], None, None
    if manifesto["faltas"]:
        erros.append(f"o manifesto tem {len(manifesto['faltas'])} faltas: resolva com "
                     f"python -m fabrica.visual {slug}")
    esperado = {i: t["visual"]["tipo"] for b in blocos(roteiro) for i, t in b["trechos"]}
    if {e["id"]: e["tipo"] for e in manifesto["trechos"]} != esperado:
        erros.append(f"manifesto desatualizado em relação ao roteiro: rode python -m fabrica.visual {slug}")
    for e in manifesto["trechos"]:
        erros += [f"{e['id']}: arquivo ausente {a}" for a in _arquivos_usados(e) if not (visual / a).exists()]
    if not (visual / "creditos.txt").exists():
        erros.append(f"arquivo ausente: {visual / 'creditos.txt'}")
    if not list((base / "musica").glob("*.mp3")):
        erros.append("nenhuma música .mp3 em historia/musica/")
    for f in (base / "fontes" / FONTE, base / "estilo" / "pergaminho.png",
              *(base / "estilo" / "objetos" / nome for nome in OBJETOS),
              base / "mascote" / "poses" / f"{POSE_CARTAO}.webp"):
        if not f.exists():
            erros.append(f"arquivo ausente: {f}")
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        erros.append("ffmpeg/ffprobe não encontrados no PATH")
    else:
        for m in sorted((base / "musica").glob("*.mp3")):
            try:
                ok = clipes.duracao(m) > clipes.CROSSFADE
            except (subprocess.CalledProcessError, ValueError):
                ok = False
            if not ok:
                erros.append(f"música inválida: {m.name}")
    return erros, roteiro, manifesto


def infos(roteiro, manifesto, base, slug):
    """O que cada evento mostra: tipo, pose, texto e arquivos de origem (caminhos absolutos)."""
    visual = base / "visual" / slug
    por_id = {e["id"]: e for e in manifesto["trechos"]}
    saida = {}
    for b in blocos(roteiro):
        if b["id"] not in ("intro", "outro"):
            saida[f"cartao.{b['id']}"] = {"tipo": "cartao", "pose": POSE_CARTAO,
                                          "numero": int(b["id"]), "titulo": b["titulo"]}
        for i, t in b["trechos"]:
            v, e = t["visual"], por_id[i]
            info = {"tipo": v["tipo"], "pose": v["mascote"], "texto": v["texto_tela"]}
            if v["tipo"] in ("acervo", "mapa"):
                arquivo = next(o["arquivo"] for o in e["opcoes"] if o["letra"] == e["escolhida"])
                info["imagem"] = str(visual / arquivo)
            elif v["tipo"] == "cena":
                info["cena"] = [str(visual / q) for q in e["quadros"]]
            anim = visual / "imagens" / f"{i}-anim.mp4"  # cena da Higgsfield ou motion graphic, se houver
            if anim.exists():
                info["animacao"] = str(anim)
            saida[i] = info
    return saida


def montar_receita(evento, info, base, pasta):
    """Gera as camadas (PNG) do evento e devolve a receita do clipe para clipes.render_clipe."""
    perg, fonte = base / "estilo" / "pergaminho.png", base / "fontes" / FONTE
    objetos = base / "estilo" / "objetos"
    pasta.mkdir(parents=True, exist_ok=True)
    nome = pasta / evento["id"]
    com_troll = bool(info["pose"])
    r = {"quadros": evento["quadros"], "troll": None}
    if info["pose"]:
        troll, (x, y) = camadas.troll(base / "mascote" / "poses" / f"{info['pose']}.webp")
    if info.get("animacao"):
        r |= {"modo": "video", "video": info["animacao"], "duracao": clipes.duracao(info["animacao"])}
    elif info["tipo"] == "cena":
        r |= {"modo": "cena", "cena": info["cena"],
              "pan": 1 if sum(map(ord, evento["id"])) % 2 else -1}
    elif info["tipo"] == "linha_tempo":
        fundo, marcos = camadas.linha_tempo(perg, fonte, info["texto"], com_troll, x_troll=x if com_troll else None)
        fundo.save(f"{nome}.png", compress_level=1)
        r |= {"modo": "marcos", "fundo": f"{nome}.png", "marcos": []}
        for k, marco in enumerate(marcos):
            marco.save(f"{nome}-m{k}.png", compress_level=1)
            r["marcos"].append(f"{nome}-m{k}.png")
    else:
        if info["tipo"] == "cartao":
            img = camadas.cartao_capitulo(perg, objetos / "pergaminho.png", fonte, info["numero"],
                                          info["titulo"])
            modo = "fixo"
        elif info["tipo"] == "texto":
            img, modo = camadas.lousa(perg, objetos / "lousa.png", fonte, info["texto"], com_troll), "zoom"
        else:
            img, modo = camadas.foto(perg, info["imagem"], com_troll), "zoom"
        if modo == "zoom":
            img = img.resize((3840, 2160))  # o zoompan trabalha em 4K para não tremer
        img.save(f"{nome}.png", compress_level=1)
        r |= {"modo": modo, "fundo": f"{nome}.png"}
    if info["pose"]:
        troll.save(f"{nome}-troll.png", compress_level=1)
        r["troll"] = {"arquivo": f"{nome}-troll.png", "x": x, "y": y}
    return r


def _origem(caminho):
    s = Path(caminho).stat()
    return f"{caminho}|{s.st_size}|{int(s.st_mtime)}"


def render_evento(evento, info, base, pasta):
    """(clipe, gerado?): reaproveita o clipe se a receita (entradas, textos, quadros) não mudou."""
    origens = [_origem(p) for p in [info.get("imagem"), info.get("animacao"), *info.get("cena", [])] if p]
    if info["pose"]:
        origens.append(_origem(base / "mascote" / "poses" / f"{info['pose']}.webp"))
    # ponytail: pergaminho, objetos (lousa/pergaminho) e fonte ficam fora da chave; se mudarem, apague historia/montagem/<slug>/clipes
    chave = json.dumps({"versao": 3, "quadros": evento["quadros"], "origens": origens, **info},
                       sort_keys=True, ensure_ascii=False)
    destino = pasta / "clipes" / f"{evento['id']}-{_hash8(chave)}.mp4"
    if destino.exists():
        return destino, False
    clipes.render_clipe(montar_receita(evento, info, base, pasta / "camadas"), destino)
    return destino, True


def _cliente_elevenlabs():
    from elevenlabs.client import ElevenLabs
    return ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])


def main(argv=None, base=BASE, criar_cliente=_cliente_elevenlabs):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m fabrica.montagem",
                                 description="Monta o vídeo longo de um roteiro do canal de história")
    ap.add_argument("slug")
    ap.add_argument("--musica", default="", help="só usa músicas cujo nome contém este texto")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0

    erros, roteiro, manifesto = checar(base, args.slug)
    if erros:
        print("\n".join(erros))
        return 2
    voz = os.environ.get("ELEVENLABS_VOZ_HISTORIA")
    if not voz:
        print("Faltando ELEVENLABS_VOZ_HISTORIA no .env.")
        return 2
    musicas = [m for m in sorted((base / "musica").glob("*.mp3")) if args.musica.lower() in m.name.lower()]
    if not musicas:
        print(f"nenhuma música em historia/musica/ contém '{args.musica}'")
        return 2
    pasta = base / "montagem" / args.slug
    bls = blocos(roteiro)
    pendentes = [b for b in bls
                 if not all(f.exists() for f in arquivos_narracao(pasta / "narracao", b, voz)[:2])]
    if pendentes:
        if not os.environ.get("ELEVENLABS_API_KEY"):
            print("Faltando ELEVENLABS_API_KEY no .env (há narração por gerar).")
            return 2
        print(f"{len(pendentes)} blocos a narrar "
              f"(~{sum(len(texto_do_bloco(b)) for b in pendentes)} caracteres)")

    cliente = []

    def obter_cliente():
        if not cliente:
            cliente.append(criar_cliente())
        return cliente[0]

    narrados = []
    for b in bls:
        try:
            wav, palavras = narrar_bloco(obter_cliente, pasta / "narracao", b, voz)
        except Exception as e:  # erro do ElevenLabs (cota, rede, chave) ou do FFmpeg no WAV
            print(f"erro na narração do bloco {b['id']}: {e}")
            return 1
        dur = clipes.duracao(wav)
        cortes, proporcional = fronteiras(palavras, [t["narracao"] for _, t in b["trechos"]], dur)
        if proporcional:
            print(f"alerta: alinhamento do bloco {b['id']} não bate; divisão proporcional")
        narrados.append({**b, "dur": dur, "wav": wav, "palavras": palavras,
                         "trechos": [(i, a, z) for (i, _), (a, z) in zip(b["trechos"], cortes)]})

    eventos, capitulos, total = linha_do_tempo(narrados)
    inf = infos(roteiro, manifesto, base, args.slug)
    lista, novos = [], 0
    for k, e in enumerate(eventos, 1):
        print(f"  {k}/{len(eventos)} {e['id']}", flush=True)
        try:
            clipe, gerado = render_evento(e, inf[e["id"]], base, pasta)
        except RuntimeError as err:
            print(f"erro no FFmpeg no evento {e['id']}: {err}")
            return 1
        lista.append(clipe)
        novos += gerado

    saida = base / "videos" / args.slug
    segmentos = []
    for b in narrados:
        if b["id"] not in ("intro", "outro"):
            segmentos.append(CARTAO)
        segmentos.append(b["wav"])
    try:
        clipes.faixa_narracao(segmentos, pasta / "narracao.wav")
        faixas = clipes.playlist(musicas, args.slug, total, {m: clipes.duracao(m) for m in musicas})
        clipes.mixar(pasta / "narracao.wav", faixas, total, pasta / "mix.m4a")
        clipes.concatenar(lista, pasta / "video_sem_audio.mp4")
        clipes.juntar(pasta / "video_sem_audio.mp4", pasta / "mix.m4a", saida / "video.mp4")
    except RuntimeError as err:
        print(f"erro no FFmpeg na junção: {err}")
        return 1

    palavras = [{**p, "inicio": p["inicio"] + c["inicio_narracao"], "fim": p["fim"] + c["inicio_narracao"]}
                for b, c in zip(narrados, capitulos) for p in b["palavras"]]
    (saida / "legendas.srt").write_text(saidas.legendas(palavras), "utf-8")
    creditos = (base / "visual" / args.slug / "creditos.txt").read_text("utf-8")
    texto = saidas.descricao(roteiro, capitulos, creditos)
    (saida / "descricao.txt").write_text(texto, "utf-8")
    if len(texto) > saidas.LIMITE_DESCRICAO:
        print(f"alerta: descricao.txt tem {len(texto)} caracteres (limite do YouTube: {saidas.LIMITE_DESCRICAO})")
    salvar_json(saida / "capitulos.json", capitulos)
    print(f"{saidas.tempo_capitulo(total)} de vídeo, {len(lista)} clipes "
          f"({novos} gerados, {len(lista) - novos} reaproveitados) → {saida}")
    return 0


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    sys.exit(main())

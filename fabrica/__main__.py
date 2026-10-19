import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path

from fabrica import IDIOMAS, etapa

EMOJI = {"pronto": "🟢", "revisar": "🟡", "descartado": "🔴", "falhou": "⚠️"}


def checar_ambiente():
    faltando = [p for p in ("ffmpeg", "ffprobe") if shutil.which(p) is None]
    faltando += [v for v in ("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY",
                             *(c["vozes_env"] for c in IDIOMAS.values()))
                 if not os.environ.get(v)]
    return faltando


def gerar_relatorio(nome, criador, idioma, itens):
    linhas = [f"# Relatório — {nome} [{idioma.upper()}]", "",
              f"{IDIOMAS[idioma]['credito']}: {criador}", ""]
    for it in itens:
        r = it.get("receita") or {}
        meta = r.get(idioma, {})
        linhas.append(f"## {EMOJI[it['status']]} {it['n']:02d} — {meta.get('titulo', '(sem título)')}")
        cabecalho = (f"- Status: {it['status']} | Score: {r.get('score', '-')} | "
                     f"Tema: {r.get('tema', it['momento']['tema'])}")
        if "arquivo" in it:
            cabecalho += (f" | {it['duracao']:.0f}s | Narração: {it['pct_narracao']:.0%}"
                          f" | Voz: {it['voz']}")
        linhas.append(cabecalho)
        if "arquivo" in it:
            linhas.append(f"- Arquivo: {it['arquivo']}")
        if it.get("motivo"):
            linhas.append(f"- Motivo: {it['motivo']}")
        linhas += [f"- ⚠️ {a}" for a in r.get("alertas", []) + it.get("alertas", [])]
        if meta:
            linhas += ["",
                       f"**YouTube:** {meta['titulo']}",
                       f"**TikTok:** {meta['tiktok_legenda']} {' '.join(meta['hashtags'])}",
                       f"**Produto:** {meta['produto']}"]
        if r:
            linhas.append("")
            for b in r["blocos"]:
                if b["tipo"] == "narracao":
                    linhas.append(f"> 🎙️ {b[idioma]}")
                else:
                    linhas.append(f"> 🎬 original {b['inicio']:.1f}s–{b['fim']:.1f}s")
        linhas.append("")
    return "\n".join(linhas)


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="fabrica", description="Vídeo longo de games -> Shorts EN/PT")
    ap.add_argument("video")
    ap.add_argument("--criador", required=True, help="Nome do canal de origem para o crédito")
    args = ap.parse_args(argv)

    from dotenv import load_dotenv
    load_dotenv()
    faltando = checar_ambiente()
    if faltando:
        sys.exit("Faltando: " + ", ".join(faltando) + ". Veja .env.example e instale o FFmpeg.")

    import anthropic
    from elevenlabs.client import ElevenLabs

    from fabrica.audio import escolher_voz, extrair_audio, ler_vozes, narrar, transcrever
    from fabrica.editorial import (DURACAO_MAX_S, DURACAO_MIN_S, MIN_NARRACAO, achar_momentos,
                                   roteirizar, status)
    from fabrica.render import duracao, render_short, slug

    video = Path(args.video).resolve()
    nome = video.stem
    work, out = Path("work") / nome, Path("output") / nome
    claude = anthropic.Anthropic()
    eleven = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    vozes = {i: ler_vozes(os.environ[c["vozes_env"]]) for i, c in IDIOMAS.items()}

    audio_mp3 = work / "audio.mp3"
    if not audio_mp3.exists():
        print("1/6 extraindo áudio...")
        extrair_audio(video, audio_mp3)
    print("2/6 transcrevendo...")
    transcricao = etapa(work / "transcricao.json", lambda: transcrever(eleven, audio_mp3))
    palavras, idioma_fonte = transcricao["palavras"], transcricao["idioma"]
    print("3/6 achando momentos...")
    momentos = etapa(work / "momentos.json", lambda: achar_momentos(claude, palavras))

    def roteirizar_todos():
        resultado = []
        for m in momentos:
            try:
                receita, erros = roteirizar(claude, palavras, m, args.criador)
            except Exception as e:  # recusa/erro de API num momento não derruba a rodada
                resultado.append({"momento": m, "receita": None, "status": "descartado",
                                  "erros": {i: [f"erro: {e}"] for i in IDIOMAS}})
                continue
            st = "descartado" if all(erros.values()) else status(receita)
            resultado.append({"momento": m, "receita": receita, "erros": erros, "status": st})
        return resultado

    print("4/6 roteirizando...")
    roteiros = etapa(work / "roteiros.json", roteirizar_todos)

    for idioma, cfg in IDIOMAS.items():
        itens = []
        for n, rt in enumerate(roteiros, 1):
            item = {"n": n, "status": rt["status"], "momento": rt["momento"],
                    "receita": rt["receita"]}
            erros = rt["erros"][idioma]
            if rt["status"] == "descartado" or erros:
                item.update(status="descartado",
                            motivo="; ".join(erros) or "score baixo ou fora de contexto")
                itens.append(item)
                continue
            try:
                receita = rt["receita"]
                nome_voz, voz_id = escolher_voz(vozes[idioma], f"{nome}:{n}:{idioma}")
                print(f"5/6 [{idioma}] narrando Short {n:02d} ({nome_voz})...")
                narracoes = []
                for k, b in enumerate(receita["blocos"]):
                    if b["tipo"] == "narracao":
                        h = hashlib.sha1(f"{voz_id}:{b[idioma]}".encode("utf-8")).hexdigest()[:8]
                        mp3 = work / "audio" / idioma / f"{n:02d}_{k:02d}_{h}.mp3"
                        pal = etapa(mp3.with_suffix(".json"),
                                    lambda: narrar(eleven, b[idioma], mp3, voz_id, idioma))
                        narracoes.append((mp3, pal))
                s_narr = sum(duracao(mp3) for mp3, _ in narracoes)
                s_orig = sum(b["fim"] - b["inicio"] for b in receita["blocos"]
                             if b["tipo"] == "original")
                total = s_narr + s_orig
                pct = s_narr / total
                if pct < MIN_NARRACAO:
                    item.update(status="descartado", motivo=f"narração real de {pct:.0%} (< 40%)")
                    itens.append(item)
                    continue
                if total < DURACAO_MIN_S:
                    item["alertas"] = ["abaixo de 60 s: não monetiza no TikTok"]
                elif total > DURACAO_MAX_S:
                    item["alertas"] = [f"{total:.0f} s, acima do alvo de 90 s: vale cortar antes de publicar"]
                print(f"6/6 [{idioma}] renderizando Short {n:02d}...")
                arquivo = out / idioma / f"{n:02d}_{rt['status']}_{slug(receita[idioma]['titulo'].removesuffix("#Shorts"))}.mp4"
                render_short(video, receita, idioma, idioma_fonte, narracoes, palavras,
                             work / idioma / f"short{n:02d}", arquivo,
                             f"{cfg['credito']}: {args.criador}")
                item.update(arquivo=arquivo.name, duracao=total, pct_narracao=pct, voz=nome_voz)
            except Exception as e:  # um Short com falha não derruba os outros
                item.update(status="falhou", motivo=str(e))
            itens.append(item)

        (out / idioma).mkdir(parents=True, exist_ok=True)
        (out / idioma / "relatorio.md").write_text(
            gerar_relatorio(nome, args.criador, idioma, itens), "utf-8")
        contagem = {s: sum(1 for i in itens if i["status"] == s) for s in EMOJI}
        print(f"Pronto [{idioma}]: {out / idioma} — "
              + ", ".join(f"{EMOJI[s]} {s}: {c}" for s, c in contagem.items() if c))


if __name__ == "__main__":
    main()

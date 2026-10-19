"""Vídeos fora da curva num tema: quantas vezes cada vídeo superou a mediana do PRÓPRIO canal.

View bruta mede o tamanho do canal; o múltiplo mede a ideia. Ideia adaptada de
https://github.com/Jakeschincariol/youtube-agent-skill (MIT, skills/yt-viral/swipe.py).
"""
import argparse
import json
import statistics
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

MIN_VIDEOS_CANAL = 4  # com menos que isso a mediana não diz nada
DURACAO_MINIMA = 180  # ignora Shorts e clipes; a comparação é com a aba Vídeos do canal
VIEWS_MINIMAS = 10_000  # abaixo disso o múltiplo é ruído de canal minúsculo


def _ytdlp(alvo, n):
    r = subprocess.run(["yt-dlp", alvo, "--flat-playlist", "--playlist-end", str(n), "-J"],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise RuntimeError(r.stderr.strip()[-300:])
    return json.loads(r.stdout).get("entries") or []


def buscar(busca, n):
    return [v for v in _ytdlp(f"ytsearch{n}:{busca}", n)
            if (v.get("view_count") or 0) >= VIEWS_MINIMAS and v.get("channel_id") and (v.get("duration") or 0) >= DURACAO_MINIMA]


def views_do_canal(channel_id, n):
    return [v["view_count"] for v in _ytdlp(f"https://www.youtube.com/channel/{channel_id}/videos", n)
            if v.get("view_count")]


def fora_da_curva(videos, views_por_canal, minimo):
    """(lista ordenada pelo múltiplo, canais ignorados por ter poucos vídeos)."""
    saida, ignorados = [], set()
    for v in videos:
        views = views_por_canal.get(v["channel_id"], [])
        if len(views) < MIN_VIDEOS_CANAL:
            ignorados.add(v.get("channel") or v["channel_id"])
            continue
        mediana = statistics.median(views)
        multiplo = v["view_count"] / mediana if mediana else 0
        if multiplo >= minimo:
            saida.append({"titulo": v.get("title", ""), "canal": v.get("channel", ""),
                          "views": v["view_count"], "mediana": int(mediana),
                          "multiplo": round(multiplo, 1), "duracao": v.get("duration"),
                          "url": v.get("url", "")})
    saida.sort(key=lambda r: -r["multiplo"])
    return saida, sorted(ignorados)


def tabela(linhas):
    """Tabela Markdown, pronta para colar em historia/referencias/<tema>.md."""
    out = ["| múltiplo | views | mediana do canal | duração | canal | vídeo |", "|---|---|---|---|---|---|"]
    for r in linhas:
        m, s = divmod(int(r["duracao"] or 0), 60)
        titulo = r["titulo"].replace("|", "/")
        out.append(f"| {r['multiplo']}x | {r['views']:,} | {r['mediana']:,} | {m}:{s:02d} | {r['canal']} "
                   f"| [{titulo}]({r['url']}) |")
    return "\n".join(out)


def main(argv=None, buscar=buscar, views_do_canal=views_do_canal):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m fabrica.referencias",
                                 description="Vídeos que superaram a mediana do próprio canal numa busca")
    ap.add_argument("busca", help='ex.: "inventors who stole inventions"')
    ap.add_argument("-n", type=int, default=30, help="quantos resultados da busca (padrão 30)")
    ap.add_argument("--canal", type=int, default=15, help="vídeos recentes por canal para a mediana")
    ap.add_argument("--min", type=float, default=1.5, dest="minimo", help="múltiplo mínimo (padrão 1.5)")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0

    videos = buscar(args.busca, args.n)
    if not videos:
        print("A busca não trouxe vídeos longos.")
        return 1
    canais = sorted({v["channel_id"] for v in videos})

    def seguro(c):  # um canal que falha só fica fora da conta
        try:
            return views_do_canal(c, args.canal)
        except (RuntimeError, ValueError):
            return []
    with ThreadPoolExecutor(6) as pool:
        views = dict(zip(canais, pool.map(seguro, canais)))
    linhas, ignorados = fora_da_curva(videos, views, args.minimo)
    print(f"{len(videos)} vídeos longos de {len(canais)} canais; fora da curva (≥ {args.minimo}x):\n")
    print(tabela(linhas) if linhas else "Nenhum passou do mínimo — tente --min 1.2 ou mais resultados (-n).")
    if ignorados:
        print(f"\nIgnorados (menos de {MIN_VIDEOS_CANAL} vídeos para a mediana): {', '.join(ignorados)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

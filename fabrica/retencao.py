"""Lê o CSV de retenção do YouTube Studio e diz onde o público saiu e o que a narração dizia ali.

Ideia adaptada de https://github.com/Jakeschincariol/youtube-agent-skill (MIT, skills/yt-retention).
"""
import argparse
import csv
import io
import re
import sys
from pathlib import Path

from fabrica import montagem

GANCHO = 30.0  # segundos iniciais que contam como "gancho"
QUEDA_MINIMA = 0.8  # pontos percentuais entre duas amostras para contar como queda


def ler_csv(texto):
    """Pares (posição, retenção) das duas primeiras colunas numéricas de cada linha.
    Aceita frações (0–1) ou porcentagens; devolve sempre a posição em % do vídeo e a retenção em %."""
    pontos = []
    for linha in csv.reader(io.StringIO(texto)):
        nums = []
        for c in linha:
            try:
                nums.append(float(c.strip().replace("%", "").replace(",", "")))
            except ValueError:
                pass
        if len(nums) >= 2:
            pontos.append((nums[0], nums[1]))
    if pontos and max(x for x, _ in pontos) <= 1.0:
        pontos = [(x * 100, y) for x, y in pontos]
    if pontos and max(y for _, y in pontos) <= 1.5:
        pontos = [(x, y * 100) for x, y in pontos]
    return pontos


def ler_srt(texto):
    """Lista de (início, fim, texto) em segundos."""
    def seg(t):
        h, m, s = t.replace(",", ".").split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    falas = []
    for bloco in texto.strip().split("\n\n"):
        m = re.search(r"([\d:,.]+)\s*-->\s*([\d:,.]+)\n(.*)", bloco, re.S)
        if m:
            falas.append((seg(m.group(1)), seg(m.group(2)), " ".join(m.group(3).split())))
    return falas


def analisar(pontos, duracao):
    """Perda no gancho, as 5 maiores quedas (com o segundo em que aconteceram) e a perda média por
    ponto percentual de vídeo depois do gancho."""
    seg = lambda x: x / 100 * duracao
    inicio = pontos[0][1]
    no_gancho = [y for x, y in pontos if seg(x) <= GANCHO]
    quedas = []
    for (x0, y0), (x1, y1) in zip(pontos, pontos[1:]):
        if y0 - y1 > QUEDA_MINIMA:
            quedas.append({"segundo": round(seg(x0), 1), "perda": round(y0 - y1, 1)})
    quedas.sort(key=lambda q: -q["perda"])
    meio = [(y0 - y1) / ((x1 - x0) or 1) for (x0, y0), (x1, y1) in zip(pontos, pontos[1:])
            if seg(x0) > GANCHO]
    return {"inicio": inicio, "fim": pontos[-1][1],
            "perda_gancho": round(inicio - min(no_gancho, default=inicio), 1),
            "quedas": quedas[:5],
            "ritmo": round(sum(meio) / len(meio), 2) if meio else 0.0}


def fala_em(falas, segundo, folga=4.0):
    return " ".join(t for a, b, t in falas if a <= segundo + folga and b >= segundo - folga)[:160]


def relatorio(r, falas=()):
    situacao = "saudável" if r["perda_gancho"] < 25 else "vazando" if r["perda_gancho"] < 40 else "grave"
    linhas = [f"Retenção: {r['inicio']:.0f}% → {r['fim']:.0f}%",
              f"GANCHO  {r['perda_gancho']:.1f} pontos perdidos nos primeiros {GANCHO:.0f} s [{situacao}]"
              " — abaixo de 25 é saudável; se não for, conserte a primeira frase antes de tudo.",
              "QUEDAS  os momentos em que o público saiu:"]
    for q in r["quedas"]:
        m, s = divmod(int(q["segundo"]), 60)
        dito = fala_em(falas, q["segundo"]) if falas else ""
        linhas.append(f"  -{q['perda']:4.1f}  em {m}:{s:02d}" + (f'  "{dito}"' if dito else ""))
    if not r["quedas"]:
        linhas.append("  nenhuma queda brusca — a perda é toda gradual")
    linhas.append(f"RITMO   {r['ritmo']:.2f} pontos perdidos por 1% de vídeo depois do gancho"
                  " (perda gradual = ritmo lento: corte, não reescreva)")
    return "\n".join(linhas)


def main(argv=None, base=montagem.BASE):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m fabrica.retencao",
                                 description="Onde o público saiu, a partir do CSV de retenção do Studio")
    ap.add_argument("csv", help="Studio → vídeo → Análise → Engajamento → gráfico de retenção → baixar")
    ap.add_argument("--slug", help="vídeo longo do canal: usa historia/videos/<slug>/legendas.srt")
    ap.add_argument("--srt", help="legenda do vídeo, se não for um vídeo longo do canal")
    ap.add_argument("--duracao", type=float, help="duração em segundos (padrão: fim da legenda)")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0

    pontos = ler_csv(Path(args.csv).read_text("utf-8-sig", errors="replace"))
    if len(pontos) < 8:
        print(f"Não achei pelo menos 8 pontos numéricos em {args.csv}.")
        return 2
    srt = Path(args.srt) if args.srt else base / "videos" / args.slug / "legendas.srt" if args.slug else None
    falas = ler_srt(srt.read_text("utf-8")) if srt and srt.exists() else []
    duracao = args.duracao or (falas[-1][1] if falas else None)
    if not duracao:
        print("Informe --slug, --srt ou --duracao para saber em que segundo cada queda aconteceu.")
        return 2
    print(relatorio(analisar(pontos, duracao), falas))
    return 0


if __name__ == "__main__":
    sys.exit(main())

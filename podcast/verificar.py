"""Confere se os vídeos de saída rodam liso no celular e no PC.

Uso: python verificar.py <pasta-do-episodio>/saida
Para cada .mp4: H.264 yuv420p + AAC 48 kHz, áudio e vídeo começando em 0 e com a mesma duração,
quadro-chave a cada ≤ 2,1 s, sem buraco nos carimbos de tempo (o que travava o celular no EP04)
e decodificação completa sem erro.
"""
import json
import subprocess
import sys
from pathlib import Path


def probe(*args):
    return json.loads(subprocess.run(["ffprobe", "-v", "error", "-of", "json", *args],
                                     capture_output=True, check=True).stdout)


def maior_salto(tempos):
    return max((b - a for a, b in zip(tempos, tempos[1:])), default=0.0)


def problemas(mp4):
    out = []
    info = probe("-show_streams", "-show_format", str(mp4))
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next(s for s in info["streams"] if s["codec_type"] == "audio")
    if (v["codec_name"], v["pix_fmt"]) != ("h264", "yuv420p"):
        out.append(f"vídeo {v['codec_name']} {v['pix_fmt']}")
    if (a["codec_name"], a["sample_rate"]) != ("aac", "48000"):
        out.append(f"áudio {a['codec_name']} {a['sample_rate']}")
    for s in (v, a):
        if abs(float(s.get("start_time", 0))) > 0.05:
            out.append(f"{s['codec_type']} começa em {s['start_time']} s")
    if abs(float(v["duration"]) - float(a["duration"])) > 0.15:
        out.append(f"vídeo {float(v['duration']):.2f} s x áudio {float(a['duration']):.2f} s")
    chaves = [float(f["pts_time"]) for f in probe("-select_streams", "v", "-skip_frame", "nokey",
                                                   "-show_entries", "frame=pts_time", str(mp4))["frames"]]
    if maior_salto(chaves + [float(v["duration"])]) > 2.1:
        out.append(f"quadro-chave a cada até {maior_salto(chaves + [float(v['duration'])]):.1f} s")
    for tipo, limite in (("v", 0.05), ("a", 0.05)):
        pts = sorted(float(p["pts_time"]) for p in probe("-select_streams", tipo, "-show_entries",
                                                          "packet=pts_time", str(mp4))["packets"])
        if maior_salto(pts) > limite:
            out.append(f"buraco de {maior_salto(pts):.2f} s no {'vídeo' if tipo == 'v' else 'áudio'}")
    erros = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp4), "-f", "null", "-"],
                           capture_output=True, text=True).stderr.strip()
    if erros:
        out.append("erro ao decodificar: " + erros.splitlines()[0])
    return out


assert maior_salto([0, 2, 2.5]) == 2 and maior_salto([]) == 0


if __name__ == "__main__":
    ruins = 0
    for mp4 in sorted(Path(sys.argv[1]).rglob("*.mp4")):
        p = problemas(mp4)
        ruins += bool(p)
        print(("FALHA " if p else "ok    ") + str(mp4.relative_to(sys.argv[1])) + ("  — " + "; ".join(p) if p else ""))
    sys.exit(1 if ruins else 0)

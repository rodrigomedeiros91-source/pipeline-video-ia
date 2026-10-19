import re
import subprocess
import unicodedata
from pathlib import Path

from fabrica import IDIOMAS

W, H = 1080, 1920

CABECALHO_ASS = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Legenda,Arial,84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,2,60,60,480,1
Style: Credito,Arial,38,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,3,0,2,40,40,80,1
Style: Selo,Arial,64,&H0000D7FF,&H0000D7FF,&H00000000,&H64000000,-1,0,0,0,100,100,4,0,1,4,0,8,40,40,160,1
Style: Gancho,Arial,74,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,3,16,0,8,80,80,250,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def tempo_ass(segundos: float) -> str:
    cs = round(segundos * 100)
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _linha(inicio, fim, estilo, texto):
    texto = texto.replace("{", "(").replace("}", ")").replace("\n", " ")
    return f"Dialogue: 0,{tempo_ass(inicio)},{tempo_ass(fim)},{estilo},,0,0,0,,{texto}\n"


GANCHO_S = 3.0  # o gancho escrito fica no topo só nos primeiros segundos, quando se decide continuar ou rolar


def gerar_ass(palavras, duracao, credito, selo=None, por_linha=3, gancho=None):
    """Legenda em blocos de `por_linha` palavras + crédito fixo + selo e gancho opcionais.
    `palavras` já com tempos relativos ao início do segmento."""
    ass = CABECALHO_ASS
    if gancho:
        ass += _linha(0, min(GANCHO_S, duracao), "Gancho", gancho)
    for i in range(0, len(palavras), por_linha):
        grupo = palavras[i:i + por_linha]
        texto = " ".join(p["texto"] for p in grupo).upper()
        ass += _linha(grupo[0]["inicio"], grupo[-1]["fim"], "Legenda", texto)
    ass += _linha(0, duracao, "Credito", credito)
    if selo:
        ass += _linha(0, duracao, "Selo", selo)
    return ass


def slug(texto: str) -> str:
    ascii_ = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")[:60]


AUDIO_NORM = "loudnorm=I=-14:TP=-1.5:LRA=11"
ENCODE = ["-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
          "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]
# Gameplay ampliado a LARGURA_ZOOM px e recortado no centro (~63% da largura de uma fonte 16:9),
# sobre a mesma imagem desfocada preenchendo o 9:16. Maior = mais zoom; W = imagem inteira.
LARGURA_ZOOM = 1700


def tela(largura=LARGURA_ZOOM):
    return (f"[0:v]split[fundo][frente];"
            f"[fundo]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=20:5[fundo2];"
            f"[frente]scale={largura}:-2,crop={W}:ih[frente2];"
            f"[fundo2][frente2]overlay=(W-w)/2:(H-h)/2")


TELA = tela()


def _ffmpeg(args, cwd=None):
    r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
                       cwd=cwd, capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise RuntimeError(f"ffmpeg falhou: {r.stderr.strip()[-500:]}")


def duracao(arquivo: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(arquivo)],
                       capture_output=True, encoding="utf-8", errors="replace", check=True)
    return float(r.stdout.strip())


def legenda_distribuida(texto: str, dur: float):
    """Fala traduzida não tem tempo por palavra: distribui as palavras por igual no trecho."""
    palavras = texto.split()
    if not palavras:
        return []
    passo = dur / len(palavras)
    return [{"texto": t, "inicio": i * passo, "fim": (i + 1) * passo}
            for i, t in enumerate(palavras)]


def inicio_gameplay(inicio: float, dur: float, dur_video: float) -> float:
    """Recua o início da narração para o gameplay caber na fonte."""
    return max(0.0, min(inicio, dur_video - dur))


def palavras_do_trecho(palavras, inicio: float, fim: float):
    """Palavras da transcrição dentro do trecho, com tempos relativos ao início dele."""
    return [{"texto": p["texto"], "inicio": p["inicio"] - inicio, "fim": p["fim"] - inicio}
            for p in palavras if p["inicio"] >= inicio and p["fim"] <= fim]


def _render_original(video, inicio, fim, palavras, seg, credito, largura=LARGURA_ZOOM, gancho=None):
    # O filtro subtitles roda com cwd na pasta do segmento e nome relativo,
    # evitando escapar "C:\" no filtro do FFmpeg no Windows.
    dur = fim - inicio
    ass = seg.with_suffix(".ass")
    ass.write_text(gerar_ass(palavras, dur, credito, gancho=gancho), "utf-8")
    fc = f"{tela(largura)},subtitles={ass.name}[v];[0:a]{AUDIO_NORM}[au]"
    _ffmpeg(["-ss", f"{inicio:.3f}", "-t", f"{dur:.3f}", "-i", str(video),
             "-filter_complex", fc, "-map", "[v]", "-map", "[au]", *ENCODE, seg.name],
            cwd=seg.parent)


def _render_narracao(video, inicio, dur, mp3, palavras, seg, credito, selo):
    # Gameplay da fonte sem som sob a narração; tpad congela o último quadro se a fonte acabar.
    ass = seg.with_suffix(".ass")
    ass.write_text(gerar_ass(palavras, dur, credito, selo=selo), "utf-8")
    fc = (f"{TELA},tpad=stop_mode=clone:stop_duration={dur:.3f},subtitles={ass.name}[v];"
          f"[1:a]{AUDIO_NORM}[au]")
    _ffmpeg(["-ss", f"{inicio:.3f}", "-t", f"{dur:.3f}", "-i", str(video), "-i", str(mp3),
             "-filter_complex", fc, "-map", "[v]", "-map", "[au]", "-t", f"{dur:.3f}",
             *ENCODE, seg.name],
            cwd=seg.parent)


def render_short(video, receita, idioma, idioma_fonte, narracoes, palavras, pasta, saida, credito):
    video, pasta, saida = Path(video).resolve(), Path(pasta).resolve(), Path(saida).resolve()
    pasta.mkdir(parents=True, exist_ok=True)
    saida.parent.mkdir(parents=True, exist_ok=True)
    dur_video = duracao(video)
    selo = IDIOMAS[idioma]["selo"]

    fila = iter(narracoes)
    segmentos = []
    for i, b in enumerate(receita["blocos"]):
        seg = pasta / f"seg{i:02d}.mp4"
        if b["tipo"] == "original":
            if idioma == idioma_fonte:
                pal = palavras_do_trecho(palavras, b["inicio"], b["fim"])
            else:
                pal = legenda_distribuida(b[f"legenda_{idioma}"], b["fim"] - b["inicio"])
            _render_original(video, b["inicio"], b["fim"], pal, seg, credito)
        else:
            mp3, pal = next(fila)
            mp3 = Path(mp3).resolve()
            dur = duracao(mp3)
            inicio = inicio_gameplay(b["inicio"], dur, dur_video)
            _render_narracao(video, inicio, dur, mp3, pal, seg, credito, selo)
        segmentos.append(seg)

    lista = pasta / "lista.txt"
    lista.write_text("".join(f"file '{s.name}'\n" for s in segmentos), "utf-8")
    _ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(saida)])

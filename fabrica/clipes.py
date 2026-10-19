"""FFmpeg do vídeo longo: clipe por evento, concatenação, trilha com ducking e vídeo final."""
import os
import random

from fabrica.render import _ffmpeg, duracao  # noqa: F401 (duracao é reexportada)

FPS = 30
VIDEO = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-r", str(FPS), "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]
CROSSFADE = 3.0
VOLUME_MUSICA = 0.12  # ~-18 dB; 0.35 abafava a narração


def _gerar(args, destino):
    """O FFmpeg grava em <nome>.tmp<ext> e renomeia: nunca sobra arquivo pela metade com o nome final."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(f"{destino.stem}.tmp{destino.suffix}")
    _ffmpeg([*args, str(tmp)])
    os.replace(tmp, destino)


# Ciclo de animação limitada: (pose, segundos). 1 base, 2 falando, 3 piscando, 4 gesto.
CICLO = ((1, 1.2), (2, 0.25), (1, 0.25), (2, 0.25), (1, 0.6), (3, 0.15), (1, 0.8), (4, 1.0),
         (2, 0.25), (4, 0.25), (2, 0.25), (4, 0.6), (3, 0.15), (4, 0.4))


def janelas_poses(n_quadros):
    """({pose: [(ini, fim)]}, duração do ciclo) — só poses que existem; as que faltam ficam na base."""
    t, janelas = 0.0, {}
    for pose, dur in CICLO:
        if 1 < pose <= n_quadros:
            janelas.setdefault(pose, []).append((round(t, 3), round(t + dur, 3)))
        t += dur
    return janelas, round(t, 3)


def _zoom(quadros, pan=0, tamanho=(1920, 1080)):
    n, s = max(quadros - 1, 1), f"{tamanho[0]}x{tamanho[1]}"
    if not pan:
        return (f"zoompan=z='1+0.05*on/{n}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":d=1:s={s}:fps={FPS}")
    progresso = f"on/{n}" if pan > 0 else f"(1-on/{n})"
    return (f"zoompan=z='1+0.08*on/{n}':x='(iw-iw/zoom)*{progresso}':y='ih/2-(ih/zoom/2)'"
            f":d=1:s={s}:fps={FPS}")


def render_clipe(r, destino):
    """Clipe sem áudio no tamanho r['tamanho'] (padrão 1920×1080), exatamente r['quadros'] quadros."""
    entradas, filtros = [], []

    def entrada(caminho):
        entradas.extend(["-loop", "1", "-framerate", str(FPS), "-i", str(caminho)])
        return f"[{entradas.count('-i') - 1}:v]"

    n = r["quadros"]
    w, h = r.get("tamanho", (1920, 1080))
    if r["modo"] == "video":
        # clipe animado (Higgsfield): roda uma vez, até 1,3x mais lento, e congela no último quadro; um zoom lento
        # contínuo cobre o resto do trecho. Nunca volta em reverso (o "bumerangue" parecia IA mal feita).
        entradas.extend(["-i", str(r["video"])])
        lento = min(max(n / FPS / r["duracao"], 1.0), 1.3)
        caixa = (w, round(w * 9 / 16)) if r.get("fundo") else (w, h)
        filtros.append(f"[0:v]setpts={lento:.3f}*PTS,fps={FPS},tpad=stop_mode=clone:stop_duration=600,"
                       f"scale={2 * caixa[0]}:{2 * caixa[1]}:force_original_aspect_ratio=increase,"
                       f"crop={2 * caixa[0]}:{2 * caixa[1]},{_zoom(n, 0, caixa)}[anim]")
        if r.get("fundo"):  # Short vertical: o clipe 16:9 fica sobre o pergaminho, centrado em r["y"]
            filtros.append(f"{entrada(r['fundo'])}[anim]overlay=0:{r['y']}-h/2[base]")
        else:
            filtros.append("[anim]null[base]")
    elif r["modo"] == "cena":
        atual = entrada(r["cena"][0])
        janelas, ciclo = janelas_poses(len(r["cena"]))
        for k, pose in enumerate(sorted(janelas)):
            ativo = "+".join(f"between(mod(t,{ciclo}),{a},{b - 0.001:.3f})" for a, b in janelas[pose])
            filtros.append(f"{atual}{entrada(r['cena'][pose - 1])}overlay=enable='{ativo}'[p{k}]")
            atual = f"[p{k}]"
        filtros.append(f"{atual}scale={2 * w}:{2 * h}:force_original_aspect_ratio=increase,"
                       f"crop={2 * w}:{2 * h},{_zoom(n, r.get('pan', 0), (w, h))}[base]")
    elif r["modo"] == "marcos":
        atual = entrada(r["fundo"])
        intervalo = n / FPS / max(len(r["marcos"]), 1)
        for k, marco in enumerate(r["marcos"]):
            filtros.append(f"{atual}{entrada(marco)}overlay=enable='gte(t,{k * intervalo:.3f})'[m{k}]")
            atual = f"[m{k}]"
        filtros.append(f"{atual}null[base]")
    elif r["modo"] == "zoom":
        filtros.append(f"{entrada(r['fundo'])}scale={2 * w}:{2 * h},{_zoom(n, r.get('pan', 0), (w, h))}[base]")
    else:
        filtros.append(f"{entrada(r['fundo'])}null[base]")
    base = "[base]"
    if r.get("topo"):
        filtros.append(f"[base]{entrada(r['topo'])}overlay=0:0[topo]")
        base = "[topo]"
    if r.get("troll"):
        t = r["troll"]
        filtros.append(f"{base}{entrada(t['arquivo'])}overlay=x={t['x']}:y='{t['y']}+6*sin(2*PI*t/2)'[f]")
    else:
        filtros.append(f"{base}null[f]")
    filtros.append("[f]scale=out_color_matrix=bt709:out_range=tv,format=yuv420p[v]")
    _gerar([*entradas, "-filter_complex", ";".join(filtros), "-map", "[v]", "-frames:v", str(n),
            *VIDEO], destino)


def concatenar(clipes, destino):
    lista = destino.with_suffix(".txt")
    lista.parent.mkdir(parents=True, exist_ok=True)
    lista.write_text("".join("file '" + c.resolve().as_posix().replace("'", "'\\''") + "'\n"
                             for c in clipes), "utf-8")
    _gerar(["-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy"], destino)


def para_wav(mp3, wav):
    _gerar(["-i", str(mp3), "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le"], wav)


def faixa_narracao(segmentos, destino):
    """Narração completa: arquivos de áudio, recortes (arquivo, ini, fim) e silêncios (float, em segundos)."""
    entradas, filtros, rotulos = [], [], []
    for s in segmentos:
        rotulo = f"[s{len(rotulos)}]"
        if isinstance(s, (int, float)):
            filtros.append(f"anullsrc=r=48000:cl=stereo:d={s:.3f}{rotulo}")
        else:
            caminho, corte = (s[0], f"atrim={s[1]:.3f}:{s[2]:.3f},asetpts=PTS-STARTPTS,") if isinstance(s, tuple) \
                else (s, "")
            entradas += ["-i", str(caminho)]
            filtros.append(f"[{len(entradas) // 2 - 1}:a]{corte}aresample=48000,"
                           f"aformat=channel_layouts=stereo{rotulo}")
        rotulos.append(rotulo)
    filtros.append(f"{''.join(rotulos)}concat=n={len(rotulos)}:v=0:a=1[a]")
    _gerar([*entradas, "-filter_complex", ";".join(filtros), "-map", "[a]", "-c:a", "pcm_s16le"],
           destino)


def playlist(faixas, slug, total, duracoes):
    """Faixas embaralhadas pelo slug (mesmo vídeo, mesma ordem), repetidas até cobrir o total."""
    curtas = [f for f in faixas if duracoes[f] <= CROSSFADE]
    if not faixas or curtas:
        raise ValueError(f"trilha inválida: sem faixas ou faixas com até {CROSSFADE:.0f} s: {curtas}")
    ordem = sorted(faixas)
    random.Random(slug).shuffle(ordem)
    lista, coberto = [], 0.0
    while coberto < total:
        for f in ordem:
            coberto += duracoes[f] - (CROSSFADE if lista else 0)
            lista.append(f)
            if coberto >= total:
                break
    return lista


def mixar(narracao, faixas, total, destino):
    """Narração + música emendada com crossfade, abaixando sob a voz (ducking), em -14 LUFS."""
    entradas = ["-i", str(narracao)]
    for f in faixas:
        entradas += ["-i", str(f)]
    filtros, atual = [], "[1:a]"
    for i in range(2, len(faixas) + 1):
        filtros.append(f"{atual}[{i}:a]acrossfade=d={CROSSFADE}[x{i}]")
        atual = f"[x{i}]"
    filtros += [
        f"{atual}atrim=0:{total:.3f},afade=t=out:st={max(total - CROSSFADE, 0):.3f}:d={CROSSFADE},"
        f"volume={VOLUME_MUSICA},aresample=48000,aformat=channel_layouts=stereo[mus]",
        "[0:a]asplit=2[narr][ctrl]",
        "[mus][ctrl]sidechaincompress=threshold=0.02:ratio=12:attack=20:release=400[duck]",
        "[narr][duck]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]",
    ]
    _gerar([*entradas, "-filter_complex", ";".join(filtros), "-map", "[a]", "-c:a", "aac",
            "-b:a", "160k", "-ar", "48000", "-ac", "2"], destino)


def juntar(video, audio, destino):
    _gerar(["-i", str(video), "-i", str(audio), "-map", "0:v", "-map", "1:a", "-c", "copy",
            "-shortest", "-movflags", "+faststart"], destino)

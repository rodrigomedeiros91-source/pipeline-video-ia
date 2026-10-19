"""Edição de podcast: episódio longo e cortes longos (16:9) e Shorts (9:16).

Uso: python cortes.py <pasta-do-episodio> episodio|longos|shorts|roteiro [--so N ...]
A pasta tem edicao.json (decisões editoriais) e falantes.json (transcrição com voz por palavra).
"""
import bisect
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # usa o pacote fabrica/ da raiz
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageStat  # noqa: E402

from fabrica import etapa  # noqa: E402
from fabrica.render import AUDIO_NORM, _ffmpeg, slug, tempo_ass  # noqa: E402

FONTE = r"C:\Windows\Fonts\ariblk.ttf"
FONTE_TEXTO = r"C:\Windows\Fonts\arialbd.ttf"
QUADRO = 1001 / 30000                      # 29,97 fps (padrão; o edicao.json pode trazer "fps")
# GOP de 2 s: com o padrão do qsv (~8 s) o celular demora a começar e engasga ao pular no vídeo
ENCODE = ["-c:v", "h264_qsv", "-preset", "medium", "-global_quality", "22", "-g", "60", "-pix_fmt", "nv12",
          "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart"]
# Shorts: x264 compatível com celular (GOP de 2 s, quadro-chave logo após a capa, sem quadros B: vídeo começa em 0).
# O h264_qsv usava GOP de 8,5 s e o celular engasgava no início (o PC não).
ENCODE_SHORT = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-profile:v", "high", "-level", "4.1",
                "-bf", "0", "-pix_fmt", "yuv420p", "-g", "60", "-keyint_min", "30", "-force_key_frames", "0,0.1",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart"]
LARGURA_9x16 = 608                         # 1080 × 9/16, arredondado para par: vídeo do Short em tela cheia
FAIXA_TOPO = 300                           # altura da faixa do título da capa
POS_FAIXA_CAPA = 1170                      # capa: faixa na altura do peito, por cima do vídeo (pedido do cliente)
MIN_FALA = 0.8                             # fala mais curta que isso ("uhum") não troca o enquadramento


# ---------- transcrição ----------

def _norm(t):
    return re.sub(r"[^\wà-ú]", "", t.lower())


def corrigir_nomes(palavras, pares):
    """Troca sequências de palavras mal transcritas (ex.: "Bar o Léu" -> "Bar ao Léu"), mantendo a pontuação.
    errados: um conjunto que vale pras duas palavras, ou uma tupla com um conjunto por palavra."""
    for errados, certo in pares:
        pos = errados if isinstance(errados, tuple) else (errados, errados)
        for i in range(len(palavras) - len(pos) + 1):
            seq = palavras[i:i + len(pos)]
            if all(_norm(p["texto"]) in e for p, e in zip(seq, pos)):
                for p, c in zip(seq, certo.split(maxsplit=len(pos) - 1)):  # sobra de palavras vai na última
                    p["texto"] = re.sub(r"\w[\w-]*", c, p["texto"], count=1)
    return palavras


assert [p["texto"] for p in corrigir_nomes([{"texto": "Léo,"}, {"texto": "Léo"}, {"texto": "Au"}, {"texto": "Léo."},
                                            {"texto": '"Bar'}, {"texto": "O"}, {"texto": "Léo?"}],
                                           [(({"bar"}, {"o"}, {"léo"}), "Bar ao Léu"), (({"au"}, {"léo"}), "ao Léu")])
        ] == ["Léo,", "Léo", "ao", "Léu.", '"Bar', "ao", "Léu?"]
assert corrigir_nomes([{"texto": "Bar"}, {"texto": "Oléo,"}], [(({"bar"}, {"oléo"}), "Bar ao Léu")])[1]["texto"] == "ao Léu,"


def _fecha_frase(texto):
    return texto.rstrip('"”’\'').endswith((".", "?", "!"))


def ajustar(a, b, palavras, inicios, quadro=QUADRO):
    """Encaixa [a, b] nas palavras: começa na 1ª palavra a partir de a e termina no fim da última frase
    completa até b (ou na última palavra, se não houver frase completa). Folga curta nas pontas."""
    i = bisect.bisect_left(inicios, a - 0.3)
    j = bisect.bisect_right(inicios, b) - 1
    if i > j:
        raise ValueError(f"trecho vazio: {a}-{b}")
    fim = next((k for k in range(j, i - 1, -1) if _fecha_frase(palavras[k]["texto"])), j)
    ini = max(palavras[i]["inicio"] - 0.12, palavras[i - 1]["fim"] if i else 0)
    seguinte = palavras[fim + 1]["inicio"] if fim + 1 < len(palavras) else palavras[fim]["fim"] + 0.3
    fim_t = min(palavras[fim]["fim"] + 0.3, seguinte - 0.02)
    # alinha ao quadro para vídeo e áudio de cada trecho terem a mesma duração
    return round(ini / quadro) * quadro, round(fim_t / quadro) * quadro


def texto(a, b, palavras):
    return " ".join(p["texto"] for p in palavras if a <= p["inicio"] < b)


# ---------- planos de câmera ----------

def _quadro(video, t, destino):
    _ffmpeg(["-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=320:-2", str(destino)])


def _faixa(img):  # faixa de cima: cenário de fundo, que não muda quando as pessoas se mexem
    return img.convert("RGB").crop((0, 0, img.width, img.height * 35 // 100)).resize((64, 12))


def detectar_planos(video, pasta, refs):
    """[[início, câmera]] de cada plano. Cortes achados nos keyframes e refinados quadro a quadro;
    câmera = referência (A/B/C) mais parecida na faixa de cima do quadro."""
    tmp = pasta / "tmp_planos"
    tmp.mkdir(exist_ok=True)
    _ffmpeg(["-skip_frame", "nokey", "-i", str(video), "-an", "-vf",
             "scale=160:-2,select='gt(scene\\,0.3)',metadata=print:file=cortes_kf.txt", "-f", "null", "-"], cwd=tmp)
    brutos = [float(x) for x in re.findall(r"pts_time:([\d.]+)", (tmp / "cortes_kf.txt").read_text())]
    cortes = [0.0]
    for t in brutos:
        a = max(0.0, t - 2.5)
        _ffmpeg(["-ss", f"{a:.3f}", "-t", "2.7", "-i", str(video), "-an", "-vf",
                 "scale=160:-2,select='gt(scene\\,0.3)',metadata=print:file=fino.txt", "-f", "null", "-"], cwd=tmp)
        finos = [float(x) for x in re.findall(r"pts_time:([\d.]+)", (tmp / "fino.txt").read_text())]
        cortes.append(a + finos[-1] if finos else t)
    ref = {}
    for cam, t in refs.items():
        _quadro(video, t, tmp / f"ref_{cam}.jpg")
        ref[cam] = _faixa(Image.open(tmp / f"ref_{cam}.jpg"))
    planos = []
    for k, t in enumerate(cortes):
        fim = cortes[k + 1] if k + 1 < len(cortes) else t + 3
        _quadro(video, t + min(1.0, (fim - t) / 2), tmp / "q.jpg")
        f = _faixa(Image.open(tmp / "q.jpg"))
        cam = min(ref, key=lambda c: sum(ImageStat.Stat(ImageChops.difference(ref[c], f)).mean))
        planos.append([t, cam])
    return planos


LOGO = Path(__file__).with_name("marca") / "logo.png"  # círculo com fundo transparente
ANIMACAO = Path(__file__).with_name("marca") / "logo_anim.mov"  # gerada por marca/animacao.py
ANIMACAO_16x9 = Path(__file__).with_name("marca") / "logo_anim_16x9.mov"
SFX_LOGO = Path(__file__).with_name("marca") / "sfx_logo.wav"
DUR_ANIMACAO = 1.9   # ao fim dela o logo animado está no canto e o logo fixo assume
DUR_CAPA = 1.0       # capa = faixa do título por cima do 1º segundo do vídeo (dá pra escolher esse quadro no YouTube)


def fim_do_gancho(palavras, de=4.0, ate=8.0, pausa=0.3, padrao=5.0):
    """Instante da 1ª pausa na fala entre `de` e `ate` s (fim do gancho); sem pausa, `padrao`."""
    for p, q in zip(palavras, palavras[1:]):
        if de <= p["fim"] <= ate and q["inicio"] - p["fim"] >= pausa:
            return p["fim"] + 0.1
    return padrao


assert fim_do_gancho([{"inicio": 0, "fim": 4.5}, {"inicio": 5.0, "fim": 6}]) == 4.6
assert fim_do_gancho([{"inicio": 0, "fim": 4.5}, {"inicio": 4.6, "fim": 9}]) == 5.0
MODELO_ROSTO =Path(__file__).with_name("modelos") / "face_detection_yunet_2023mar.onnx"  # opencv_zoo, Apache-2.0
JANELA = 8.0          # o operador muda o zoom dentro do plano: rostos refeitos a cada 8 s no máximo
TOLERANCIA_X = 80     # diferença menor que isso entre pedaços vizinhos não move o quadro (evita tremida)


class Rostos:
    """Rostos [centro x, largura, confiança] (em 1920 px) num instante do vídeo, com cache em disco."""

    def __init__(self, video, cache):
        import cv2
        self.video, self.cache_path = video, cache
        self.cache = json.loads(cache.read_text()) if cache.exists() else {}
        self.det = cv2.FaceDetectorYN.create(str(MODELO_ROSTO), "", (960, 540), 0.6)

    def __call__(self, t):
        k = f"{t:.2f}"
        if k not in self.cache:
            import numpy as np
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(self.video), "-frames:v", "1",
                                  "-vf", "scale=960:540", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                                 capture_output=True, check=True).stdout
            _, f = self.det.detect(np.frombuffer(raw, np.uint8).reshape(540, 960, 3))
            self.cache[k] = sorted([round((x + w / 2) * 2), round(w * 2), float(s)]
                                   for x, y, w, h, *_, s in (f if f is not None else []) if w * 2 >= 50)
            self.cache_path.write_text(json.dumps(self.cache))
        return self.cache[k]


def visiveis(cam, rostos, cfg):
    """{voz: x} de quem aparece no quadro. 4+ rostos = plano geral (ordem da mesa em cfg["geral"]);
    menos = as pessoas da câmera do plano, casadas pela posição esperada."""
    if len(rostos) >= 4:
        quatro = sorted(sorted(rostos, key=lambda r: -r[2])[:4])
        return {v: r[0] for v, r in zip(cfg["geral"], quatro)}
    esperado = cfg["cameras"].get(cam, {})
    if not rostos:
        return dict(esperado)
    if len(rostos) == len(esperado):
        return {v: r[0] for v, r in zip(sorted(esperado, key=esperado.get), rostos)}
    out = {}
    for v, xe in esperado.items():
        r = min(rostos, key=lambda r: abs(r[0] - xe))
        if abs(r[0] - xe) < 450:
            out[v] = r[0]
    return out


def enquadrar(a, b, planos, palavras, inicios, cfg, rostos):
    """Pedaços [(t0, t1, x)] de [a, b]: x = centro do rosto de quem fala, se ele aparece no quadro;
    senão, quem estava sendo mostrado ou o primeiro visível de cfg["prioridade"]."""
    ini_planos = [p[0] for p in planos]
    pedacos, atual = [], None
    k = bisect.bisect_right(ini_planos, a) - 1
    while k < len(planos) and planos[k][0] < b:
        s0 = max(a, planos[k][0])
        s1 = min(b, planos[k + 1][0] if k + 1 < len(planos) else b)
        n = max(1, round((s1 - s0) / JANELA + 0.49))
        for j in range(n):
            w0, w1 = s0 + j * (s1 - s0) / n, s0 + (j + 1) * (s1 - s0) / n
            vis = visiveis(planos[k][1], rostos((w0 + w1) / 2), cfg)
            falas = []  # [início, fim, voz] de cada fala contínua de alguém visível
            for p in palavras[bisect.bisect_left(inicios, w0):bisect.bisect_left(inicios, w1)]:
                v = p["voz"] if p["voz"] in vis else None
                if falas and falas[-1][2] == v:
                    falas[-1][1] = p["fim"]
                else:
                    falas.append([p["inicio"], p["fim"], v])
            falas = [f for f in falas if f[2] and f[1] - f[0] >= MIN_FALA]
            if falas:
                atual = falas[0][2]
            elif atual not in vis:
                atual = next((v for v in cfg["prioridade"] if v in vis), None)
            t = w0
            for f0, _, v in falas[1:]:
                if v != atual:
                    corte = max(t, f0 - 0.15)
                    pedacos.append((t, corte, vis.get(atual, 960), atual if atual in vis else None))
                    t, atual = corte, v
            pedacos.append((t, w1, vis.get(atual, 960), atual if atual in vis else None))
        k += 1
    suave = []
    for t0, t1, x, voz in pedacos:  # voz = quem está enquadrado (None = ninguém em especial)
        if suave and suave[-1][3] == voz and abs(suave[-1][2] - x) < TOLERANCIA_X:  # só junta a mesma pessoa
            suave[-1] = (suave[-1][0], t1, *suave[-1][2:])
        else:
            suave.append((t0, t1, x, voz))
    return [p for p in suave if p[1] - p[0] > 0.01]


# ---------- camadas ----------

def tarja(nome, cargo, destino):
    """Tarja de nome 1920×1080 no canto inferior esquerdo: faixa preta com filete dourado."""
    img = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f1, f2 = ImageFont.truetype(FONTE, 52), ImageFont.truetype(FONTE_TEXTO, 34)
    larg = max(d.textlength(nome, font=f1), d.textlength(cargo, font=f2)) + 80
    d.rectangle((90, 850, 90 + larg, 990), fill=(10, 10, 10, 225))
    d.rectangle((90, 850, 102, 990), fill=(232, 182, 46, 255))
    d.text((130, 862), nome, font=f1, fill="white")
    d.text((130, 934), cargo, font=f2, fill=(232, 182, 46, 255))
    img.save(destino)


ASS_9x16 = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Legenda,Arial Black,80,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,7,3,2,50,50,560,1
Style: Nome,Arial,40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,2,50,50,470,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
DOURADO = "&H2EB6E8&"


SELO = "NOME DO PODCAST  •  SLOGAN"  # troque pelo do seu programa
FONTE_FAIXA = r"C:\Windows\Fonts\bahnschrift.ttf"   # fonte variável do Windows (usamos Bold Condensed)
OURO_RGB = (232, 182, 46)


def _bahn(tam, estilo="Bold Condensed"):
    f = ImageFont.truetype(FONTE_FAIXA, tam)
    f.set_variation_by_name(estilo)
    return f


def palavras_destaque(titulo):
    """[(palavra, dourada)]: o trecho entre [colchetes] no título sai em dourado."""
    out, dentro = [], False
    for w in titulo.upper().split():
        ini, fim = "[" in w, "]" in w            # o colchete pode vir colado em pontuação: "MESA]:"
        out.append((w.replace("[", "").replace("]", ""), dentro or ini))
        dentro = (dentro or ini) and not fim
    return out


assert palavras_destaque("o [dono bateu]: já") == [("O", False), ("DONO", True), ("BATEU:", True), ("JÁ", False)]


def faixa_titulo(titulo):
    """Faixa 1080×FAIXA_TOPO do topo do Short: degradê escuro, selo dourado, título branco com destaque
    dourado (até 3 linhas, tamanho ajustado) e filete dourado na base. O logo entra por cima depois."""
    W, H, x0 = 1080, FAIXA_TOPO, 190          # x0: à direita do logo (140 px + margens)
    larg, topo, base = W - x0 - 36, 78, H - 26
    img = Image.new("RGBA", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        c = round(24 - 14 * y / H)
        d.line((0, y, W, y), fill=(c, c, c, 255))
    for x in range(W):  # filete dourado, mais claro no centro
        k = 1 - abs(x - W / 2) / (W / 2)
        d.line((x, H - 6, x, H), fill=(round(190 + 55 * k), round(140 + 70 * k), round(30 + 70 * k), 255))
    d.text((x0, 30), SELO, font=_bahn(26, "SemiBold"), fill=OURO_RGB)
    palavras = palavras_destaque(titulo)
    for tam in range(70, 38, -2):
        f = _bahn(tam)
        esp = d.textlength(" ", font=f)
        linhas, atual, w_atual = [], [], 0
        for p, ouro in palavras:
            w = d.textlength(p, font=f)
            if atual and w_atual + esp + w > larg:
                linhas.append(atual)
                atual, w_atual = [], 0
            w_atual += (esp if atual else 0) + w
            atual.append((p, ouro, w))
        linhas.append(atual)
        alt = round(tam * 1.04)
        if len(linhas) <= 3 and alt * len(linhas) <= base - topo:
            break
    sombra = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ds, dt = ImageDraw.Draw(sombra), ImageDraw.Draw(img)
    y = topo + (base - topo - alt * len(linhas)) // 2
    for linha in linhas:
        x = x0
        for p, ouro, w in linha:
            ds.text((x + 3, y + 4), p, font=f, fill=(0, 0, 0, 200))
            dt.text((x, y), p, font=f, fill=OURO_RGB if ouro else (255, 255, 255))
            x += w + esp
        y += alt
    return Image.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(3)), img)


def camada_capa(titulo):
    """Camada 1080×1920 transparente: faixa do título com o logo, na altura do peito."""
    img = Image.new("RGBA", (1080, 1920))
    img.alpha_composite(faixa_titulo(titulo), (0, POS_FAIXA_CAPA))
    img.alpha_composite(Image.open(LOGO).convert("RGBA").resize((140, 140), Image.LANCZOS), (20, POS_FAIXA_CAPA + 80))
    return img


def grupos_legenda(palavras, max_palavras=3, max_chars=18):
    """Blocos curtos: quebra em pontuação, pausa > 0,5 s, 3 palavras ou 18 letras."""
    grupos, atual = [], []
    for p in palavras:
        if atual and (len(atual) == max_palavras or p["inicio"] - atual[-1]["fim"] > 0.5
                      or len(" ".join(x["texto"] for x in atual + [p])) > max_chars):
            grupos.append(atual)
            atual = []
        atual.append(p)
        if re.search(r"[.?!,]$", p["texto"].rstrip('"”')):
            grupos.append(atual)
            atual = []
    return grupos + [atual] if atual else grupos


def ass_vertical(palavras, dur, nome, t_nome):
    """Legenda palavra a palavra (a palavra falada em dourado) e nome do convidado no começo."""
    def linha(i, f, estilo, txt):
        return f"Dialogue: 0,{tempo_ass(i)},{tempo_ass(f)},{estilo},,0,0,0,,{txt}\n"
    ass = ASS_9x16 + linha(t_nome, min(t_nome + 4.0, dur), "Nome", nome)  # t_nome: quando o convidado aparece
    eventos = []
    for g in grupos_legenda(palavras):
        limpas = [p["texto"].upper().strip('"“”') for p in g]
        for k, p in enumerate(g):
            fim = g[k + 1]["inicio"] if k + 1 < len(g) else p["fim"] + 0.15
            txt = " ".join(f"{{\\c{DOURADO}}}{w}{{\\c&HFFFFFF&}}" if j == k else w for j, w in enumerate(limpas))
            eventos.append([p["inicio"], fim, txt])
    for k, (i, f, txt) in enumerate(eventos):  # nunca duas legendas ao mesmo tempo (o libass empilharia)
        f = min(f, eventos[k + 1][0]) if k + 1 < len(eventos) else f
        ass += linha(i, max(f, i + 0.05), "Legenda", txt)
    return ass


def srt(palavras):
    def ts(s):
        ms = round(s * 1000)
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    blocos = grupos_legenda(palavras, max_palavras=9, max_chars=42)
    return "".join(f"{n}\n{ts(g[0]['inicio'])} --> {ts(g[-1]['fim'])}\n{' '.join(p['texto'] for p in g)}\n\n"
                   for n, g in enumerate(blocos, 1))


# ---------- render ----------

class Episodio:
    def __init__(self, pasta):
        self.pasta = Path(pasta).resolve()
        self.cfg = json.loads((self.pasta / "edicao.json").read_text("utf-8"))
        self.video = Path(self.cfg["video"])
        self.palavras = corrigir_nomes(json.loads((self.pasta / "falantes.json").read_text("utf-8")),
                                       [(tuple(map(set, e)) if isinstance(e[0], list) else set(e), c)
                                        for e, c in self.cfg.get("corrigir", [])])
        self.inicios = [p["inicio"] for p in self.palavras]
        self.planos = etapa(self.pasta / "planos.json",
                            lambda: detectar_planos(self.video, self.pasta, self.cfg["referencias"]))
        self.saida = self.pasta / "saida"
        self.rostos = Rostos(self.video, self.pasta / "rostos.json")

    def trechos(self, lista):
        quadro = 1 / self.cfg["fps"] if "fps" in self.cfg else QUADRO  # EP02 é 30 fps cravado
        return [ajustar(a, b, self.palavras, self.inicios, quadro) for a, b in lista]

    def palavras_montagem(self, trechos):
        """Palavras dos trechos com o tempo na montagem final."""
        out, base = [], 0.0
        for a, b in trechos:
            for p in self.palavras[bisect.bisect_left(self.inicios, a):bisect.bisect_left(self.inicios, b)]:
                if p["fim"] <= b + 0.05:
                    out.append({**p, "inicio": p["inicio"] - a + base, "fim": min(p["fim"], b) - a + base})
            base += b - a
        return out

    def horizontal(self, trechos, destino, tarjas=(), segurar_fim=0.0, n_gancho=0, t_logo=None):
        """Junta trechos 16:9 com tarja de nome nos tempos pedidos (tempo da fonte) e áudio normalizado.
        Os n_gancho primeiros trechos (gancho) saem em preto e branco; logo depois deles (ou em t_logo) entra a
        animação do logo com efeito sonoro, que pousa no canto superior esquerdo e fica fixo até o fim."""
        png = self.pasta / "tarja.png"
        tarja(self.cfg["convidado"]["nome"], self.cfg["convidado"]["cargo"], png)
        args, fc = [], ""
        for i, (a, b) in enumerate(trechos):
            args += ["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(self.video)]
        n = extra = len(trechos)
        for i, (a, b) in enumerate(trechos):
            dur = b - a
            janelas = [(max(t0, a) - a, min(t1, b) - a) for t0, t1 in tarjas if t0 < b and t1 > a]
            v = f"[{i}:v]setpts=PTS-STARTPTS" + (",hue=s=0" if i < n_gancho else "")
            if janelas:  # uma entrada da tarja por trecho: cada entrada só pode ser usada uma vez no filtro
                args += ["-i", str(png)]
                cond = "+".join(f"between(t,{x:.2f},{y:.2f})" for x, y in janelas)
                fc += f"{v}[b{i}];[b{i}][{extra}:v]overlay=0:0:enable='{cond}'"
                extra += 1
            else:
                fc += v
            au = f"[{i}:a]asetpts=PTS-STARTPTS,afade=t=in:d=0.03,afade=t=out:st={max(0, dur - 0.06):.3f}:d=0.06"
            if segurar_fim and i == n - 1:
                fc += f",tpad=stop_mode=clone:stop_duration={segurar_fim}"
                au += f",apad=pad_dur={segurar_fim}"
            fc += f"[v{i}];{au}[a{i}];"
        fc += "".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vc][ac]"
        if n_gancho or t_logo is not None:
            durs = [b - a for a, b in trechos]
            t0 = sum(durs[:n_gancho]) if t_logo is None else t_logo
            fim = sum(durs[:-1]) if segurar_fim else sum(durs)  # o logo fixo some no cartão final do episódio
            args += ["-i", str(LOGO), "-itsoffset", f"{t0:.3f}", "-i", str(ANIMACAO_16x9), "-i", str(SFX_LOGO)]
            fc += (f";[vc][{extra + 1}:v]overlay=0:0:eof_action=pass[vn];[{extra}:v]scale=150:150[lg];"
                   f"[vn][lg]overlay=30:24:enable='between(t,{t0 + DUR_ANIMACAO:.3f},{fim:.3f})'[v];"
                   f"[ac]{AUDIO_NORM},aresample=48000[an];[{extra + 2}:a]adelay={round(t0 * 1000)}:all=1,volume=0.7[sfx];"
                   f"[an][sfx]amix=inputs=2:duration=first:normalize=0,asetpts=N/SR/TB[a]")  # tempo do áudio contínuo
        else:
            fc += f";[vc]null[v];[ac]{AUDIO_NORM},asetpts=N/SR/TB[a]"
        destino.parent.mkdir(parents=True, exist_ok=True)
        _ffmpeg([*args, "-filter_complex", fc, "-map", "[v]", "-map", "[a]", *ENCODE, str(destino)])
        destino.with_suffix(".srt").write_text(srt(self.palavras_montagem(trechos)), "utf-8")

    def vertical(self, trechos, titulo, destino, t_logo=None, pb=0):
        """Short 9:16 em tela cheia: (chamada +) pergunta + resposta, vídeo seguindo quem fala, legenda e
        animação do logo em t_logo (padrão: fim do gancho). No 1º segundo a faixa do título fica por cima
        na altura do peito: é a capa (pedido do cliente), salva também como `<short>.capa.jpg`.
        Os pb primeiros trechos (a chamada) saem em preto e branco."""
        args, fc, pedacos = [], "", []
        for i, (a, b) in enumerate(trechos):
            pedacos.append(enquadrar(a, b, self.planos, self.palavras, self.inicios, self.cfg, self.rostos))
            expr = self._expr(pedacos[-1], a)
            args += ["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(self.video)]
            fc += (f"[{i}:v]setpts=PTS-STARTPTS,crop={LARGURA_9x16}:1080:x='{expr}':y=0,"
                   f"scale=1080:1920:flags=lanczos,setsar=1{',hue=s=0' if i < pb else ''}[v{i}];[{i}:a]asetpts=PTS-STARTPTS,"
                   f"afade=t=in:d=0.03,afade=t=out:st={max(0, b - a - 0.06):.3f}:d=0.06[a{i}];")
        n = len(trechos)
        dur = sum(b - a for a, b in trechos)
        ass = destino.with_suffix(".ass")
        destino.parent.mkdir(parents=True, exist_ok=True)
        palavras = self.palavras_montagem(trechos)
        # tarja de nome: 1º trecho longo com o convidado enquadrado, depois da capa
        convidado, base, t_nome = self.cfg["prioridade"][0], 0.0, 0.0
        for (a, b), ps in zip(trechos, pedacos):
            p = next((p for p in ps if p[3] == convidado and p[1] - p[0] >= 2), None)
            if p:
                t_nome = base + p[0] - a
                break
            base += b - a
        ass.write_text(ass_vertical(palavras, dur, self.cfg["convidado"]["tag"], max(t_nome, DUR_CAPA)), "utf-8")
        t0 = fim_do_gancho(palavras) if t_logo is None else t_logo  # animação por cima da fala, sem pausar
        camada = destino.with_suffix(".png")
        camada_capa(titulo).save(camada)
        args += ["-i", str(LOGO), "-itsoffset", f"{t0:.3f}", "-i", str(ANIMACAO), "-i", str(SFX_LOGO), "-i", camada.name]
        fc += ("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vc][ac];"
               f"[vc][{n + 1}:v]overlay=0:0:eof_action=pass[vn];[vn]subtitles='{ass.name}'[va];"  # legenda por cima da animação
               f"[{n}:v]scale=120:120[lg];[va][lg]overlay=24:14:enable='gte(t,{t0 + DUR_ANIMACAO:.3f})'[vl];"
               f"[vl][{n + 3}:v]overlay=0:0:enable='lt(t,{DUR_CAPA})'[v];"
               f"[ac]{AUDIO_NORM},aresample=48000[an];"
               f"[{n + 2}:a]adelay={round(t0 * 1000)}:all=1,volume=0.7[sfx];"
               # loudnorm deixava carimbos de tempo irregulares no início do áudio e o celular congelava a
               # imagem tentando sincronizar (o PC ignora): renumera pelo nº de amostras.
               f"[an][sfx]amix=inputs=2:duration=first:normalize=0,asetpts=N/SR/TB[a]")
        _ffmpeg([*args, "-filter_complex", fc, "-map", "[v]", "-map", "[a]", *ENCODE_SHORT, destino.name], cwd=destino.parent)
        ass.unlink()
        camada.unlink()
        _ffmpeg(["-ss", f"{DUR_CAPA / 2}", "-i", destino.name, "-frames:v", "1", "-q:v", "2",
                 destino.with_suffix(".capa.jpg").name], cwd=destino.parent)
    @staticmethod
    def _x(x):
        return min(max(round(x - LARGURA_9x16 / 2), 0), 1920 - LARGURA_9x16)

    def _expr(self, pedacos, a):
        """Expressão do crop: x de cada pedaço conforme o tempo t (relativo ao início do trecho)."""
        expr = str(self._x(pedacos[-1][2]))
        for t0, t1, x, _ in reversed(pedacos[:-1]):
            expr = f"if(lt(t,{t1 - a:.3f}),{self._x(x)},{expr})"
        return expr

    def mapa(self, trechos):
        """Converte tempo da fonte em tempo da montagem (None se o tempo foi cortado)."""
        def f(t):
            base = 0.0
            for a, b in trechos:
                if a - 1 <= t < b:
                    return base + max(0.0, t - a)
                base += b - a
            return None
        return f


def hms(s):
    s = int(s)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def pagina_aprovacao(ep):
    """HTML com cada Short (capa, chamada, vídeo), cada corte longo (gancho, vídeo) e o episódio."""
    from html import escape
    from fabrica.render import duracao

    def cartao(arq, titulo, extra, vertical, thumb=None):
        mp4 = ep.saida / arq
        try:
            d = duracao(mp4)
        except (FileNotFoundError, subprocess.CalledProcessError):  # ausente ou ainda sendo gravado
            return f'<div class="card falta"><b>{escape(titulo)}</b><p>arquivo ausente ou incompleto: {escape(arq)}</p></div>'
        capa = ep.saida / thumb if thumb else mp4.with_suffix(".capa.jpg")
        poster = f' poster="{escape(capa.relative_to(ep.saida).as_posix())}"' if capa.exists() else ""
        alerta = ' class="alerta"' if vertical and d > 90 else ""
        return (f'<div class="card{" v" if vertical else ""}"><video controls preload="none"{poster} '
                f'src="{escape(mp4.relative_to(ep.saida).as_posix())}"></video><b>{escape(titulo)}</b>'
                f'<span{alerta}>{hms(d)}</span><p>{escape(extra)}</p></div>')

    textos = lambda trs: " ".join(texto(a, b, ep.palavras) for a, b in ep.trechos(trs))
    shorts = "".join(cartao(f"shorts/{n:02d} - {slug(c['titulo'])}.mp4", f"{n:02d}. {c['titulo'].replace('[', '').replace(']', '')}",
                            "Chamada: " + textos([c["chamada"]]) if "chamada" in c else "", True)
                     for n, c in enumerate(ep.cfg["shorts"], 1))
    longos = "".join(cartao(f"longos/{n:02d} - {slug(c['titulo'])}.mp4", f"{n:02d}. {c['titulo']}",
                            "Gancho: " + textos(c.get("gancho", [])), False, f"thumbnails IA/thumbnail IA - longo {n:02d}.jpg")
                     for n, c in enumerate(ep.cfg["longos"], 1))
    episodio = "".join(cartao(m.name, "Episódio completo — " + m.stem.split("episodio completo")[-1].strip(" -") or "",
                              "", False, "thumbnails IA/thumbnail IA - episodio completo.jpg")
                       for m in sorted(ep.saida.glob(f"{ep.cfg['nome']} - episodio completo*.mp4")))
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Aprovação — {escape(ep.cfg['nome'])}</title>
<style>
body{{margin:0;background:#0f0f0f;color:#eee;font:15px/1.4 "Segoe UI",Arial,sans-serif;padding:16px}}
h1{{color:#e8b62e;margin:0 0 4px}} h2{{border-left:4px solid #e8b62e;padding-left:8px;margin:28px 0 12px}}
.grade{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}}
.grade.l{{grid-template-columns:repeat(auto-fill,minmax(420px,1fr))}}
.card{{background:#1a1a1a;border:1px solid #333;border-radius:10px;padding:10px}}
.card video{{width:100%;border-radius:6px;background:#000}} .card.v video{{aspect-ratio:9/16}}
.card b{{display:block;margin-top:8px}} .card span{{color:#e8b62e;font-weight:600}} .card span.alerta{{color:#ff5a5a}}
.card p{{color:#aaa;font-size:13px;margin:6px 0 0}} .falta{{border-color:#ff5a5a}}
</style></head><body>
<h1>{escape(ep.cfg['nome'])}</h1><p>Para aprovar: assista, anote o número do que precisa mudar.</p>
<h2>{len(ep.cfg['shorts'])} Shorts / Reels (até 90 s)</h2><div class="grade">{shorts}</div>
<h2>{len(ep.cfg['longos'])} cortes longos</h2><div class="grade l">{longos}</div>
{f'<h2>Episódio</h2><div class="grade l">{episodio}</div>' if episodio else ''}</body></html>"""


EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"  # imprime o LEIA-ME em PDF


def montar_entrega(ep, base=None):
    """Pasta pronta pra arrastar pro Drive: vídeos por tipo (hard links, sem duplicar no disco) + LEIA-ME em PDF."""
    import os
    import shutil
    from html import escape
    from fabrica.render import duracao

    cfg, pub = ep.cfg, ep.cfg["publicacao"]
    raiz = Path(base) / cfg["nome"] if base else ep.saida / f"{cfg['nome']} (entrega)"  # base: ex. pasta do Drive

    def por(origem, pasta, nome):
        destino = raiz / pasta / nome
        destino.parent.mkdir(parents=True, exist_ok=True)
        if not destino.exists():
            try:
                os.link(origem, destino)
            except OSError:
                shutil.copy2(origem, destino)

    episodios = sorted(ep.saida.glob(f"{cfg['nome']} - episodio completo*.mp4"))  # pode haver opções (A, B…)
    # sem episódio (ex.: EP02, já publicado pelo cliente) as pastas são renumeradas a partir dos cortes longos
    nomes = (["Episódio completo"] if episodios else []) + ["Cortes longos 10-12 min", "Cortes médios 5-7 min", "Shorts e Reels"]
    pastas = [f"{i}. {n}" for i, n in enumerate(nomes, 1)]
    p_longos, p_medios, p_shorts = pastas[-3:]
    for mp4 in episodios:
        por(mp4, pastas[0], mp4.name)
        por(mp4.with_suffix(".srt"), pastas[0], mp4.with_suffix(".srt").name)
    if episodios:
        por(ep.saida / "thumbnails IA" / "thumbnail IA - episodio completo.jpg", pastas[0], "thumbnail.jpg")
    arqs_cap = sorted(ep.saida.glob("capitulos*.txt"))
    capitulos = "\n".join((f"Capítulos ({c.stem.removeprefix('capitulos - ')}):\n" if len(arqs_cap) > 1 else "")
                          + c.read_text("utf-8") for c in arqs_cap)
    opcoes = ""
    if len(episodios) > 1:
        itens = "".join(f"<li>{escape(m.stem.split('episodio completo - ')[-1])}</li>" for m in episodios)
        opcoes = f"<p><b>Há {len(episodios)} opções do episódio — escolha uma:</b> {escape(pub.get('nota_episodio', ''))}</p><ul>{itens}</ul>"
    linhas_longos, linhas_shorts = "", ""
    for n, c in enumerate(cfg["longos"], 1):
        mp4 = ep.saida / "longos" / f"{n:02d} - {slug(c['titulo'])}.mp4"
        d = duracao(mp4)
        pasta = p_longos if d >= 600 else p_medios
        por(mp4, pasta, mp4.name)
        por(mp4.with_suffix(".srt"), pasta, mp4.with_suffix(".srt").name)
        thumb = ep.saida / "thumbnails IA" / f"thumbnail IA - longo {n:02d}.jpg"
        if thumb.exists():
            por(thumb, pasta, f"{n:02d} - thumbnail.jpg")
        linhas_longos += (f"<tr><td>{n:02d}</td><td>{escape(c['titulo'])}</td><td>{hms(d)}</td><td>{escape(pasta)}</td>"
                          f"<td>{escape(c['titulo'])} — {escape(pub['credito'])} no {escape(pub.get('programa', 'podcast'))}. "
                          f"Episódio completo no canal. {escape(pub['hashtags'])}</td></tr>")
    for n, c in enumerate(cfg["shorts"], 1):
        mp4 = ep.saida / "shorts" / f"{n:02d} - {slug(c['titulo'])}.mp4"
        por(mp4, p_shorts, mp4.name)
        por(mp4.with_suffix(".capa.jpg"), p_shorts, mp4.with_suffix(".capa.jpg").name)
        titulo = c["titulo"].replace("[", "").replace("]", "")
        linhas_shorts += (f"<tr><td>{n:02d}</td><td>{escape(titulo)}</td><td>{hms(duracao(mp4))}</td>"
                          f"<td>{escape(c.get('pergunta', ''))}</td></tr>")
    secao_ep = item_ep = dia_d = ""
    if episodios:
        titulos = "".join(f"<li>{escape(t)}</li>" for t in pub["titulos"])
        item_ep = f"<li><b>{pastas[0]}</b> — vídeo, thumbnail, legenda (.srt) e capítulos (abaixo).</li>"
        secao_ep = f"""<h2>Episódio completo (YouTube)</h2>{opcoes}<b>Título — escolha 1:</b><ul>{titulos}</ul>
<b>Descrição:</b><pre>{escape(pub['descricao'])}\n\n{escape(capitulos)}\n{escape(pub['links'])}\n\n{escape(pub['hashtags'])}</pre>
<b>Tags:</b> {escape(pub['tags'])}<br><b>No Studio:</b> legenda .srt (Português), tela final nos últimos 16 s."""
        dia_d = "<li><b>Dia D:</b> episódio completo no YouTube.</li>"
    html = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>LEIA-ME</title><style>
@page{{size:A4;margin:14mm}} body{{font:10.5pt/1.45 "Segoe UI",Arial,sans-serif;color:#161616}}
h1{{background:#111;color:#e8b62e;padding:12px 16px;border-radius:8px;font-size:18pt;margin:0 0 10px}}
h2{{border-left:4px solid #e8b62e;padding-left:8px;font-size:13pt;margin:18px 0 6px}}
table{{width:100%;border-collapse:collapse;font-size:9pt}} th,td{{border-bottom:1px solid #ddd;padding:4px;text-align:left;vertical-align:top}}
th{{background:#111;color:#fff}} pre{{white-space:pre-wrap;background:#f6f3ea;padding:8px;border-radius:6px;font:9pt Consolas,monospace}}
.caixa{{background:#f6f3ea;border-radius:8px;padding:8px 12px}}</style></head><body>
<h1>{escape(cfg['nome'])} — entrega</h1>
<div class="caixa"><b>O que tem aqui</b><ul>
{item_ep}
<li><b>{p_longos}</b> e <b>{p_medios}</b> — vídeo, thumbnail (quando houver) e legenda de cada um.</li>
<li><b>{p_shorts}</b> — {len(cfg['shorts'])} vídeos de até 90 s + a capa de cada um (.capa.jpg, para subir como capa no Instagram/TikTok;
no YouTube, escolha o 1º quadro do vídeo como capa).</li></ul>
<b>Para aprovar:</b> abra o vídeo aqui no Drive e use <b>Comentar</b> (ou responda no WhatsApp com o número, ex.: "Short 12", "Longo 7").</div>
{secao_ep}
<h2>Cortes longos e médios (YouTube)</h2>
<table><tr><th>#</th><th>Título</th><th>Duração</th><th>Pasta</th><th>Descrição sugerida</th></tr>{linhas_longos}</table>
<h2>Shorts e Reels (YouTube, Instagram, TikTok)</h2>
<p>Legenda do post: título + pergunta + <code>#shorts #podcast</code>. Fixe a pergunta como 1º comentário.</p>
<table><tr><th>#</th><th>Título</th><th>Duração</th><th>Pergunta pro comentário fixado</th></tr>{linhas_shorts}</table>
<h2>Calendário sugerido</h2><ul>
{dia_d}
<li><b>D a D+29:</b> 1 Short por dia no YouTube e o mesmo Reel no Instagram, na ordem dos números (os mais fortes primeiro).</li>
<li><b>A cada 2-3 dias:</b> um corte longo ou médio no YouTube, alternando os dois tamanhos.</li></ul>
</body></html>"""
    leia = raiz / "LEIA-ME.html"
    leia.write_text(html, "utf-8")
    pdf = raiz / "LEIA-ME - como usar esta entrega.pdf"
    subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--user-data-dir={ep.pasta / 'tmp_edge'}", f"--print-to-pdf={pdf}", leia.as_uri()], check=True)
    leia.unlink()
    shutil.rmtree(ep.pasta / "tmp_edge", ignore_errors=True)
    return raiz


def main():
    pasta, modo, *resto = sys.argv[1:]
    so = {int(x) for x in resto[resto.index("--so") + 1:]} if "--so" in resto else None
    ep = Episodio(pasta)
    cfg = ep.cfg
    if modo == "episodio":
        e = cfg["episodio"]
        # episódio = material completo com edição básica: sem gancho, vinheta animada do logo logo no início
        trechos = ep.trechos(e["partes"]) + [tuple(e["fim"])]
        destino = ep.saida / f"{cfg['nome']} - episodio completo.mp4"
        ep.horizontal(trechos, destino, cfg["tarjas"], e.get("segurar_fim", 0), t_logo=0.3)
        f = ep.mapa(trechos)
        caps = [f"0:00 {e['capitulos'][0][1]}"] + [f"{hms(f(t))} {nome}" for t, nome in e["capitulos"][1:]]
        destino.with_name("capitulos.txt").write_text("\n".join(caps) + "\n", "utf-8")
        print(destino)
    elif modo == "longos":
        for n, c in enumerate(cfg["longos"], 1):
            if so and n not in so:
                continue
            gancho = ep.trechos(c.get("gancho", []))
            trechos = gancho + ep.trechos(c["trechos"])
            destino = ep.saida / "longos" / f"{n:02d} - {slug(c['titulo'])}.mp4"
            ep.horizontal(trechos, destino, cfg["tarjas"] + c.get("tarjas", []), n_gancho=len(gancho))
            print(destino, round(sum(b - a for a, b in trechos)), "s")
    elif modo == "shorts":
        for n, c in enumerate(cfg["shorts"], 1):
            if so and n not in so:
                continue
            chamada = ep.trechos([c["chamada"]]) if "chamada" in c else []  # gancho antes da pergunta
            trechos = chamada + ep.trechos(c["trechos"])
            destino = ep.saida / "shorts" / f"{n:02d} - {slug(c['titulo'])}.mp4"
            ep.vertical(trechos, c["titulo"], destino, chamada[0][1] - chamada[0][0] if chamada else None, pb=len(chamada))
            print(destino, round(sum(b - a for a, b in trechos)), "s")
    elif modo == "entrega":  # pasta organizada para arrastar no Google Drive do cliente
        print(montar_entrega(ep, resto[0] if resto else None))
    elif modo == "aprovacao":  # página local com todos os vídeos renderizados, para revisar antes de entregar
        destino = ep.saida / "aprovacao.html"
        destino.write_text(pagina_aprovacao(ep), "utf-8")
        print(destino)
    elif modo == "roteiro":  # confere texto e duração de cada corte sem renderizar
        for grupo in ("shorts", "longos"):
            for n, c in enumerate(cfg[grupo], 1):
                if so and n not in so:
                    continue
                trechos = ep.trechos(c.get("gancho", []) + ([c["chamada"]] if "chamada" in c else []) + c["trechos"])
                dur = sum(b - a for a, b in trechos)
                print(f"\n== {grupo} {n} ({dur:.0f}s) {c['titulo']}")
                if grupo == "shorts":
                    for a, b in trechos:
                        print(f"  [{a:.1f}-{b:.1f}] {texto(a, b, ep.palavras)}")
                else:
                    print(f"  início: {texto(*trechos[0], ep.palavras)[:150]}")
                    print(f"  fim: ...{texto(*trechos[-1], ep.palavras)[-150:]}")


if __name__ == "__main__":
    main()

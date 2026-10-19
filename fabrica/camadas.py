"""Camadas paradas do vídeo longo (Pillow): pergaminho, foto, lousa, linha do tempo, cartão e troll."""
import re

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1080
TROLL_ALTURA, TROLL_LARGURA_MAX, TROLL_DIREITA, TROLL_BAIXO = 778, 700, 115, 22
CENTRO_COM_TROLL, CENTRO_SEM_TROLL, CENTRO_Y, CENTRO_CARTAO = 690, 960, 540, 540
FOTO_MAX = (1000, 860)
BORDA = 16
VERMELHO, TINTA, GIZ = "#B3261E", "#2B2118", "#F2F2EA"


def _cobrir(img, w, h):
    escala = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * escala), round(img.height * escala)), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def pergaminho(caminho):
    return _cobrir(Image.open(caminho).convert("RGB"), W, H)


def troll(caminho):
    """Pose recortada pela área desenhada, dentro da caixa 700×778, e a posição (x, y) à direita."""
    img = Image.open(caminho).convert("RGBA")
    img = img.crop(img.getchannel("A").getbbox())
    escala = min(TROLL_ALTURA / img.height, TROLL_LARGURA_MAX / img.width)
    img = img.resize((round(img.width * escala), round(img.height * escala)), Image.LANCZOS)
    return img, (W - img.width - TROLL_DIREITA, H - img.height - TROLL_BAIXO)


def _centro(com_troll):
    return CENTRO_COM_TROLL if com_troll else CENTRO_SEM_TROLL


def _colar(fundo, cartao, cx, cy=CENTRO_Y):
    """Cola o cartão inclinado (−2° como na maquete; no Pillow o ângulo positivo gira para a esquerda) com sombra."""
    cartao = cartao.rotate(2, resample=Image.BICUBIC, expand=True)
    sombra = Image.new("RGBA", cartao.size, (0, 0, 0, 0))
    sombra.putalpha(cartao.getchannel("A").point(lambda a: a * 45 // 100))
    sombra = sombra.filter(ImageFilter.GaussianBlur(12))
    x, y = cx - cartao.width // 2, cy - cartao.height // 2
    fundo.alpha_composite(sombra, (x + 10, y + 10))
    fundo.alpha_composite(cartao, (x, y))


def foto(fundo, imagem, com_troll):
    base = pergaminho(fundo).convert("RGBA")
    img = Image.open(imagem)
    if img.mode in ("RGBA", "LA", "P"):
        img = Image.alpha_composite(Image.new("RGBA", img.size, "white"), img.convert("RGBA"))
    img = img.convert("RGB")
    escala = min(FOTO_MAX[0] / img.width, FOTO_MAX[1] / img.height)
    img = img.resize((round(img.width * escala), round(img.height * escala)), Image.LANCZOS)
    cartao = Image.new("RGBA", (img.width + 2 * BORDA, img.height + 2 * BORDA), "white")
    cartao.paste(img, (BORDA, BORDA))
    _colar(base, cartao, _centro(com_troll))
    return base.convert("RGB")


def _quebrar(texto, fonte, largura):
    linhas = []
    for palavra in texto.split():
        if linhas and fonte.getlength(f"{linhas[-1]} {palavra}") <= largura:
            linhas[-1] += f" {palavra}"
        else:
            linhas.append(palavra)
    return linhas


def ajustar_texto(texto, fonte, largura, maior=110, menor=48, max_linhas=3):
    """(tamanho, linhas): o maior tamanho, descendo de 4 em 4, em que o texto cabe em max_linhas."""
    for tam in range(maior, menor - 1, -4):
        linhas = _quebrar(texto, ImageFont.truetype(str(fonte), tam), largura)
        if len(linhas) <= max_linhas:
            return tam, linhas
    linhas = _quebrar(texto, ImageFont.truetype(str(fonte), menor), largura)
    if len(linhas) > max_linhas:
        linhas = linhas[:max_linhas]
        linhas[-1] += "…"
    return menor, linhas


def partes_linha_tempo(texto):
    """'1775 ride → 1860 poem' → [('1775', 'ride'), ('1860', 'poem')]; parte sem número fica sem data."""
    partes = []
    for parte in (p.strip() for p in re.split(r"[→·]", texto)):
        if not parte:
            continue
        primeiro, _, resto = parte.partition(" ")
        partes.append((primeiro, resto.strip()) if any(c.isdigit() for c in primeiro) else ("", parte))
    return partes


def marcos_linha(fonte, partes, x0, x1, cy, tela, tam_data=96, tam_legenda=56):
    """Uma camada RGBA (do tamanho da tela) por marco, espaçados de x0 a x1 na altura cy."""
    n = len(partes)
    xs = [(x0 + x1) // 2] if n == 1 else [round(x0 + i * (x1 - x0) / (n - 1)) for i in range(n)]
    f_data = ImageFont.truetype(str(fonte), tam_data)
    f_legenda = ImageFont.truetype(str(fonte), tam_legenda)
    marcos = []
    for i, ((data, legenda), x) in enumerate(zip(partes, xs)):
        lado = "l" if i == 0 and n > 1 else "r" if i == n - 1 and n > 1 else "m"
        m = Image.new("RGBA", tela, (0, 0, 0, 0))
        d = ImageDraw.Draw(m)
        d.ellipse((x - 14, cy - 14, x + 14, cy + 14), fill=VERMELHO, outline=TINTA, width=3)
        if data:
            d.text((x, cy - 40), data, font=f_data, fill=TINTA, anchor=f"{lado}s")
        if legenda:
            d.text((x, cy + 40), legenda, font=f_legenda, fill=TINTA, anchor=f"{lado}a")
        marcos.append(m)
    return marcos


def linha_tempo(fundo, fonte, texto, com_troll, x_troll=None):
    """Fundo (pergaminho + traço) e uma camada RGBA por marco."""
    partes = partes_linha_tempo(texto)
    x0, x1 = 140, 1780
    if com_troll:
        x1 = min(1180, x_troll - 150) if x_troll else 1180
    base = pergaminho(fundo)
    ImageDraw.Draw(base).line((x0, CENTRO_Y, x1, CENTRO_Y), fill=TINTA, width=6)
    return base, marcos_linha(fonte, partes, x0, x1, CENTRO_Y, (W, H))


def _caber(texto, fonte, largura, altura, maior, menor=40, max_linhas=3):
    """(tamanho, linhas): o maior tamanho (de 4 em 4) que cabe na largura E na altura."""
    for tam in range(maior, menor - 1, -4):
        linhas = _quebrar(texto, ImageFont.truetype(str(fonte), tam), largura)
        if len(linhas) <= max_linhas and len(linhas) * round(tam * 1.2) <= altura:
            return tam, linhas
    return menor, _quebrar(texto, ImageFont.truetype(str(fonte), menor), largura)[:max_linhas]


def _objeto_com_texto(fundo, objeto, fonte, blocos, largura, cx, cor):
    """Pergaminho de fundo + objeto (PNG RGBA) com a largura dada centrado em (cx, CENTRO_Y),
    e as linhas de cada bloco [(linhas, tamanho)] centralizadas sobre ele."""
    base = pergaminho(fundo).convert("RGBA")
    o = Image.open(objeto).convert("RGBA")
    o = o.resize((largura, round(o.height * largura / o.width)), Image.LANCZOS)
    base.alpha_composite(o, (cx - o.width // 2, CENTRO_Y - o.height // 2))
    fontes = [(linhas, ImageFont.truetype(str(fonte), tam)) for linhas, tam in blocos]
    y = CENTRO_Y - sum(len(l) * round(f.size * 1.2) for l, f in fontes) // 2
    d = ImageDraw.Draw(base)
    for linhas, f in fontes:
        for linha in linhas:
            d.text((cx, y), linha, font=f, fill=cor, anchor="ma")
            y += round(f.size * 1.2)
    return base.convert("RGB")


def _altura(objeto, largura):
    w, h = Image.open(objeto).size
    return round(h * largura / w)


def lousa(fundo, objeto, fonte, texto, com_troll):
    """Texto a giz numa lousa; à esquerda do troll ou centralizada sem ele."""
    largura, cx = (900, 640) if com_troll else (1100, CENTRO_SEM_TROLL)
    tam, linhas = _caber(texto, fonte, round(largura * 0.76), round(_altura(objeto, largura) * 0.66),
                         maior=120)
    return _objeto_com_texto(fundo, objeto, fonte, [(linhas, tam)], largura, cx, GIZ)


def cartao_capitulo(fundo, objeto, fonte, numero, titulo, largura=940):
    """Cartão de capítulo: pergaminho aberto com "#n" e o título em tinta."""
    tam, linhas = _caber(titulo, fonte, round(largura * 0.56), round(_altura(objeto, largura) * 0.56) - 120,
                         maior=90)
    return _objeto_com_texto(fundo, objeto, fonte, [([f"#{numero}"], 100), (linhas, tam)],
                             largura, CENTRO_CARTAO, TINTA)

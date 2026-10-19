"""Camadas verticais (1080×1920) dos Shorts: fundo, gancho, foto, lousa, linha do tempo, cena, cartão final, troll."""
from PIL import Image, ImageDraw, ImageFont

from fabrica import camadas

W, H = 1080, 1920
CX, CY = 540, 810                       # centro da área do visual (1000×900, topo em y=360)
GANCHO = (110, 330)                     # faixa do gancho no topo
FOTO_MAX = (940, 840)
TROLL_CAIXA, TROLL_CANTO = (460, 560), (1060, 1420)
LINHA = (110, 970)
TEXTO_ATE = 830                         # com o troll (topo em y≥860), texto da lousa e legendas acabam aqui
CY_TROLL = 730                          # altura da linha do tempo quando o troll aparece


def fundo(perg):
    return camadas._cobrir(Image.open(perg).convert("RGB"), W, H)


def _escrever(img, fonte, blocos, cor, cy):
    """Linhas de cada bloco [(linhas, tamanho)] centralizadas em (CX, cy)."""
    fontes = [(linhas, ImageFont.truetype(str(fonte), tam)) for linhas, tam in blocos]
    y = cy - sum(len(l) * round(f.size * 1.2) for l, f in fontes) // 2
    d = ImageDraw.Draw(img)
    for linhas, f in fontes:
        for linha in linhas:
            d.text((CX, y), linha, font=f, fill=cor, anchor="ma")
            y += round(f.size * 1.2)


def gancho(fonte, texto):
    """Camada RGBA só com o gancho, até 2 linhas, na faixa do topo."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    tam, linhas = camadas._caber(texto, fonte, 940, 190, maior=96, menor=48, max_linhas=2)
    _escrever(img, fonte, [(linhas, tam)], camadas.TINTA, sum(GANCHO) // 2)
    return img


def troll(caminho):
    """Pose recortada pela área desenhada, dentro de 460×560, com o canto inferior direito em (1060, 1420)."""
    img = Image.open(caminho).convert("RGBA")
    img = img.crop(img.getchannel("A").getbbox())
    escala = min(TROLL_CAIXA[0] / img.width, TROLL_CAIXA[1] / img.height)
    img = img.resize((round(img.width * escala), round(img.height * escala)), Image.LANCZOS)
    return img, (TROLL_CANTO[0] - img.width, TROLL_CANTO[1] - img.height)


def foto(perg, imagem):
    base = fundo(perg).convert("RGBA")
    img = Image.open(imagem)
    if img.mode in ("RGBA", "LA", "P"):
        img = Image.alpha_composite(Image.new("RGBA", img.size, "white"), img.convert("RGBA"))
    img = img.convert("RGB")
    escala = min(FOTO_MAX[0] / img.width, FOTO_MAX[1] / img.height)
    img = img.resize((round(img.width * escala), round(img.height * escala)), Image.LANCZOS)
    cartao = Image.new("RGBA", (img.width + 2 * camadas.BORDA, img.height + 2 * camadas.BORDA), "white")
    cartao.paste(img, (camadas.BORDA, camadas.BORDA))
    camadas._colar(base, cartao, CX, CY)
    return base.convert("RGB")


def _lousa(perg, objeto, fonte, blocos, cy=CY):
    base = fundo(perg).convert("RGBA")
    o = Image.open(objeto).convert("RGBA")
    o = o.resize((1000, round(o.height * 1000 / o.width)), Image.LANCZOS)
    base.alpha_composite(o, (CX - o.width // 2, CY - o.height // 2))
    _escrever(base, fonte, blocos, camadas.GIZ, cy)
    return base.convert("RGB")


def lousa(perg, objeto, fonte, texto, com_troll=False):
    """Com o troll, o texto fica na faixa da lousa acima dele (topo + 60 até TEXTO_ATE), sem cobri-lo."""
    largura, altura = Image.open(objeto).size
    altura = round(altura * 1000 / largura)
    if not com_troll:
        tam, linhas = camadas._caber(texto, fonte, 760, round(altura * 0.66), maior=120)
        return _lousa(perg, objeto, fonte, [(linhas, tam)])
    topo = CY - altura // 2 + 60
    tam, linhas = camadas._caber(texto, fonte, 760, TEXTO_ATE - topo, maior=120)
    return _lousa(perg, objeto, fonte, [(linhas, tam)], (topo + TEXTO_ATE) // 2)


def cartao_final(perg, objeto, fonte, pergunta=""):
    """Lousa final; com pergunta, ela vem em destaque e o convite ao vídeo longo fica menor."""
    if not pergunta.strip():
        return _lousa(perg, objeto, fonte, [(["Full story on YouTube"], 80), (["The Myth Troll"], 110)])
    tam, linhas = camadas._caber(pergunta, fonte, 760, 250, maior=84, menor=48)
    return _lousa(perg, objeto, fonte, [(linhas, tam), (["Full story on YouTube:"], 52), (["The Myth Troll"], 76)])


def linha_tempo(perg, fonte, texto, com_troll=False):
    cy = CY_TROLL if com_troll else CY
    base = fundo(perg)
    ImageDraw.Draw(base).line((LINHA[0], cy, LINHA[1], cy), fill=camadas.TINTA, width=6)
    marcos = camadas.marcos_linha(fonte, camadas.partes_linha_tempo(texto), LINHA[0], LINHA[1], cy, (W, H),
                                  tam_data=80, tam_legenda=48)
    return base, marcos


def cena(perg, quadros):
    """Cada pose composta numa tela 1080×1920: cena 3:2 com 1080 de largura, centrada em CY."""
    saida = []
    for q in quadros:
        base = fundo(perg)
        img = Image.open(q).convert("RGB")
        img = img.resize((W, round(img.height * W / img.width)), Image.LANCZOS)
        base.paste(img, (0, CY - img.height // 2))
        saida.append(base)
    return saida

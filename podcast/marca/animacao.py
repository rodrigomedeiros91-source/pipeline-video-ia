"""Gera marca/logo_anim.mov (Shorts 1080×1920) e marca/logo_anim_16x9.mov (cortes longos e episódio 1920×1080),
com transparência, ~1,9 s: o logo surge com onda dourada, recebe um brilho e voa até o canto superior esquerdo,
onde o cortes.py mantém o logo fixo. Também gera o efeito sonoro marca/sfx_logo.wav.
Uso: python animacao.py"""
import math
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

AQUI = Path(__file__).parent
FPS = 30000 / 1001
# (largura, altura, centro do pop, tamanho no pop, centro no canto, tamanho no canto, arquivo); o canto e o
# tamanho final batem com o logo fixo do cortes.py (Shorts: 120 px em 24,14; 16:9: 150 px em 30,24)
FORMATOS = [(1080, 1920, (540, 1080), 360, (24 + 60, 14 + 60), 120, "logo_anim.mov"),      # Short: altura do peito
            (1920, 1080, (960, 600), 340, (30 + 75, 24 + 75), 150, "logo_anim_16x9.mov")]  # entre as pessoas
F_POP, F_ASSENTA, F_BRILHO, F_VOO = 10, 6, 20, 21
DOURADO = (232, 182, 46)


def back_out(x, s=1.9):  # passa um pouco do tamanho final e volta (efeito "pop")
    x -= 1
    return x * x * ((s + 1) * x + s) + 1


def in_out(x):
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def brilho(logo, pos):
    """Faixa diagonal clara atravessando o logo; pos de 0 a 1."""
    w, h = logo.size
    faixa = Image.new("L", (w * 3, h * 3), 0)
    ImageDraw.Draw(faixa).rectangle((int(w * 1.3), 0, int(w * 1.55), h * 3), fill=170)
    faixa = faixa.filter(ImageFilter.GaussianBlur(w // 25)).rotate(25)
    dx = int((pos - 0.5) * 2.4 * w)
    faixa = faixa.crop((w - dx, h, 2 * w - dx, 2 * h))
    luz = Image.new("RGBA", (w, h), (255, 245, 210, 0))
    luz.putalpha(ImageChops.multiply(faixa, logo.getchannel("A")))
    return Image.alpha_composite(logo, luz)


def animacao(W, H, CENTRO, GRANDE, CANTO, PEQUENO, arquivo):
    base = Image.open(AQUI / "logo.png").convert("RGBA").resize((GRANDE * 2, GRANDE * 2), Image.LANCZOS)
    # folga transparente em volta do logo: o brilho dourado some suave, sem bater na borda e virar quadrado
    m = round(base.width * 0.35)
    tela = Image.new("RGBA", (base.width + 2 * m, base.height + 2 * m), (0, 0, 0, 0))
    tela.alpha_composite(base, (m, m))
    halo_alfa = tela.getchannel("A").filter(ImageFilter.GaussianBlur(40))
    total = F_POP + F_ASSENTA + F_BRILHO + F_VOO
    with tempfile.TemporaryDirectory() as tmp:
        for f in range(total):
            quadro = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            cx, cy, lado, onda, pos_brilho = *CENTRO, GRANDE, None, None
            if f < F_POP:
                x = (f + 1) / F_POP
                lado = max(2, GRANDE * back_out(x))
                onda = x
            elif f < F_POP + F_ASSENTA:
                onda = 1 + (f - F_POP) / F_ASSENTA
            elif f < F_POP + F_ASSENTA + F_BRILHO:
                pos_brilho = (f - F_POP - F_ASSENTA) / (F_BRILHO - 1)
            else:
                x = in_out((f - F_POP - F_ASSENTA - F_BRILHO + 1) / F_VOO)
                cx = CENTRO[0] + (CANTO[0] - CENTRO[0]) * x
                cy = CENTRO[1] + (CANTO[1] - CENTRO[1]) * x
                lado = GRANDE + (PEQUENO - GRANDE) * x
            if onda is not None:  # anel dourado que se expande e some
                r = GRANDE * (0.5 + 0.45 * onda)
                a = int(220 * max(0.0, 1 - onda / 2))
                d = ImageDraw.Draw(quadro)
                d.ellipse((CENTRO[0] - r, CENTRO[1] - r, CENTRO[0] + r, CENTRO[1] + r), outline=DOURADO + (a,), width=10)
            forca = 1.0 if f < F_POP + F_ASSENTA + F_BRILHO else 1 - x  # o brilho em volta some durante o voo
            halo = Image.new("RGBA", tela.size, DOURADO + (0,))
            halo.putalpha(halo_alfa.point(lambda v: round(v * 0.85 * forca)))
            logo = brilho(tela, pos_brilho) if pos_brilho is not None else tela
            logo = Image.alpha_composite(halo, logo)
            lado_tela = round(logo.width * lado / base.width)
            logo = logo.resize((lado_tela, lado_tela), Image.LANCZOS)
            quadro.alpha_composite(logo, (round(cx - lado_tela / 2), round(cy - lado_tela / 2)))
            quadro.save(Path(tmp) / f"f{f:03d}.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "30000/1001", "-i", str(Path(tmp) / "f%03d.png"),
                        "-c:v", "qtrle", "-pix_fmt", "argb", str(AQUI / arquivo)], check=True)
    print(AQUI / arquivo, f"{total / FPS:.2f}s")


def main():
    for formato in FORMATOS:
        animacao(*formato)
    # Efeito sonoro sintetizado (sem direitos autorais), no mesmo tempo da animação:
    # impacto grave + estalo no pop, brilho cristalino no reflexo, whoosh no voo até o canto.
    t_brilho = round((F_POP + F_ASSENTA) / FPS * 1000)
    t_voo = round((F_POP + F_ASSENTA + F_BRILHO) / FPS * 1000)
    fontes = ["sine=f=62:d=0.7", "anoisesrc=d=0.06:c=white:a=0.7",
              "sine=f=2093:d=0.7", "sine=f=3136:d=0.7", "sine=f=4186:d=0.7", "anoisesrc=d=0.7:c=pink:a=0.6"]
    grafo = (
        "[0]afade=t=out:d=0.7:curve=exp,volume=1.6[grave];"
        "[1]highpass=f=1800,afade=t=out:d=0.06,volume=0.6[estalo];"
        "[2][3][4]amix=inputs=3,afade=t=in:d=0.01,afade=t=out:st=0.02:d=0.65:curve=exp,volume=0.5,"
        f"adelay={t_brilho}:all=1[brilho];"
        "[5]highpass=f=500,lowpass=f=7000,afade=t=in:d=0.35:curve=exp,afade=t=out:st=0.35:d=0.35,"
        f"adelay={t_voo}:all=1[whoosh];"
        "[grave][estalo][brilho][whoosh]amix=inputs=4:duration=longest:normalize=0,aformat=channel_layouts=stereo"
    )
    args = [x for f in fontes for x in ("-f", "lavfi", "-i", f)]
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args, "-filter_complex", grafo, "-ar", "48000",
                    str(AQUI / "sfx_logo.wav")], check=True)


if __name__ == "__main__":
    main()

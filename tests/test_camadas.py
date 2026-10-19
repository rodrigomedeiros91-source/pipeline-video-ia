from pathlib import Path

import pytest
from PIL import Image

from fabrica import camadas

FONTE = Path(__file__).resolve().parent.parent / "historia" / "fontes" / "PatrickHand-Regular.ttf"
TINTA = (43, 33, 24)


@pytest.fixture
def perg(tmp_path):
    caminho = tmp_path / "perg.png"
    Image.new("RGB", (64, 36), (233, 220, 192)).save(caminho)
    return caminho


@pytest.fixture
def objetos(tmp_path):
    Image.new("RGBA", (1400, 852), (30, 50, 40, 255)).save(tmp_path / "lousa.png")
    Image.new("RGBA", (1347, 927), (240, 225, 190, 255)).save(tmp_path / "pergaminho.png")
    return tmp_path


def perto(a, b, tol=8):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def test_pergaminho_cobre_a_tela(perg):
    img = camadas.pergaminho(perg)
    assert img.size == (1920, 1080) and img.mode == "RGB"


def test_troll_recortado_e_posicionado(tmp_path):
    pose = Image.new("RGBA", (400, 500), (0, 0, 0, 0))
    pose.paste((200, 0, 0, 255), (100, 50, 300, 450))
    pose.save(tmp_path / "neutro.png")
    img, (x, y) = camadas.troll(tmp_path / "neutro.png")
    assert img.size == (389, 778)
    assert img.getchannel("A").getbbox() == (0, 0, 389, 778)
    assert (x, y) == (1920 - 389 - 115, 1080 - 778 - 22)


def test_troll_largo_fica_na_caixa(tmp_path):
    pose = Image.new("RGBA", (1536, 1024), (0, 0, 0, 0))
    pose.paste((200, 0, 0, 255), (0, 0, 1536, 1024))
    pose.save(tmp_path / "deitado.png")
    img, (x, y) = camadas.troll(tmp_path / "deitado.png")
    assert img.width == 700 and img.height == round(1024 * 700 / 1536)
    assert (x, y) == (1920 - 700 - 115, 1080 - img.height - 22)


def test_foto_com_e_sem_troll(tmp_path, perg):
    Image.new("RGB", (300, 400), (0, 0, 255)).save(tmp_path / "azul.jpg")
    com = camadas.foto(perg, tmp_path / "azul.jpg", True)
    sem = camadas.foto(perg, tmp_path / "azul.jpg", False)
    assert com.size == (1920, 1080) and com.mode == "RGB"
    assert perto(com.getpixel((690, 540)), (0, 0, 255), 20)
    assert perto(com.getpixel((1250, 540)), (233, 220, 192))
    assert perto(sem.getpixel((1250, 540)), (0, 0, 255), 20)


def test_ajustar_texto_curto_fica_grande():
    assert camadas.ajustar_texto("Check the source.", FONTE, 884) == (110, ["Check the source."])


def test_ajustar_texto_longo_encolhe():
    texto = "Tortured? No. Years in prison? No. Comfortable house arrest with a view? Yes."
    tam, linhas = camadas.ajustar_texto(texto, FONTE, 884)
    assert 48 <= tam < 110 and 1 <= len(linhas) <= 3


def test_ajustar_texto_corta_com_reticencias():
    tam, linhas = camadas.ajustar_texto(" ".join(["unbelievably"] * 60), FONTE, 884)
    assert tam == 48 and len(linhas) == 3 and linhas[-1].endswith("…")


@pytest.mark.parametrize("texto,esperado", [
    ("1775 ride → 1860 poem", [("1775", "ride"), ("1860", "poem")]),
    ("1765 quote · 1770 Marie reaches France", [("1765", "quote"), ("1770", "Marie reaches France")]),
    ("1981 → 1983 → Einstein?", [("1981", ""), ("1983", ""), ("", "Einstein?")]),
    ("1969", [("1969", "")]),
])
def test_partes_linha_tempo(texto, esperado):
    assert camadas.partes_linha_tempo(texto) == esperado


def test_linha_tempo_camadas(perg):
    base, marcos = camadas.linha_tempo(perg, FONTE, "1775 ride → 1860 poem", True)
    assert base.size == (1920, 1080) and base.mode == "RGB"
    assert perto(base.getpixel((660, 540)), TINTA)
    assert len(marcos) == 2 and all(m.mode == "RGBA" and m.size == (1920, 1080) for m in marcos)
    assert perto(marcos[0].getpixel((140, 540)), (179, 38, 30, 255))
    assert perto(marcos[1].getpixel((1180, 540)), (179, 38, 30, 255))
    assert marcos[0].getpixel((1180, 540))[3] == 0


def test_linha_tempo_respeita_o_troll(perg):
    base, marcos = camadas.linha_tempo(perg, FONTE, "1775 ride → 1860 poem", True, x_troll=1016)
    assert perto(marcos[1].getpixel((866, 540)), (179, 38, 30, 255))
    assert all(m.getchannel("A").getbbox()[2] <= 866 + 16 for m in marcos)


def test_linha_tempo_um_marco_no_centro(perg):
    _, marcos = camadas.linha_tempo(perg, FONTE, "1969", False)
    assert len(marcos) == 1 and perto(marcos[0].getpixel((960, 540)), (179, 38, 30, 255))


def test_lousa_com_troll(perg, objetos):
    img = camadas.lousa(perg, objetos / "lousa.png", FONTE, "7 quotes. 0 said them.", True)
    assert img.size == (1920, 1080) and img.mode == "RGB"
    assert perto(img.getpixel((640, 540 - 548 // 2 + 15)), (30, 50, 40))
    assert perto(img.getpixel((1300, 540)), (233, 220, 192))


def test_lousa_texto_cabe():
    texto = " ".join(["history"] * 30)
    altura = 360
    tam, linhas = camadas._caber(texto, FONTE, 684, altura, maior=120)
    assert len(linhas) <= 3 and len(linhas) * round(tam * 1.2) <= altura


def test_cartao_capitulo_pergaminho(perg, objetos):
    img = camadas.cartao_capitulo(perg, objetos / "pergaminho.png", FONTE, 7,
                                  "Apollo 13 Never Said 'Houston, We Have a Problem'")
    assert img.size == (1920, 1080) and img.mode == "RGB"
    assert perto(img.getpixel((540, 540 - 323 + 20)), (240, 225, 190))
    assert perto(img.getpixel((1015, 540)), (233, 220, 192))

from pathlib import Path

import pytest
from PIL import Image, ImageChops

from fabrica import vertical

FONTE = Path(__file__).resolve().parent.parent / "historia" / "fontes" / "PatrickHand-Regular.ttf"
PARCH = (233, 220, 192)


def perto(a, b, tol=12):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


@pytest.fixture
def perg(tmp_path):
    Image.new("RGB", (64, 36), PARCH).save(tmp_path / "perg.png")
    return tmp_path / "perg.png"


@pytest.fixture
def lousa(tmp_path):
    Image.new("RGBA", (1400, 852), (30, 50, 40, 255)).save(tmp_path / "lousa.png")
    return tmp_path / "lousa.png"


def test_fundo(perg):
    img = vertical.fundo(perg)
    assert img.size == (1080, 1920) and img.mode == "RGB"


def test_gancho_fica_na_faixa_do_topo():
    img = vertical.gancho(FONTE, "She never said \"Let them eat cake\" and here is why it matters")
    assert img.size == (1080, 1920) and img.mode == "RGBA"
    x0, y0, x1, y1 = img.getchannel("A").getbbox()
    assert 60 <= x0 and x1 <= 1020 and 110 <= y0 and y1 <= 330


def test_troll_cabe_na_caixa(tmp_path):
    pose = Image.new("RGBA", (1536, 1024), (0, 0, 0, 0))
    pose.paste((200, 0, 0, 255), (0, 0, 1536, 1024))
    pose.save(tmp_path / "deitado.png")
    img, (x, y) = vertical.troll(tmp_path / "deitado.png")
    assert img.width <= 460 and img.height <= 560
    assert (x + img.width, y + img.height) == (1060, 1420)


def test_foto_no_centro_da_area(tmp_path, perg):
    Image.new("RGB", (300, 400), (0, 0, 255)).save(tmp_path / "azul.jpg")
    img = vertical.foto(perg, tmp_path / "azul.jpg")
    assert img.size == (1080, 1920)
    assert perto(img.getpixel((540, 810)), (0, 0, 255), 20)
    assert perto(img.getpixel((540, 1600)), PARCH)


def test_lousa_e_cartao_final(perg, lousa):
    img = vertical.lousa(perg, lousa, FONTE, "Spoiled? Yes. Cake monster? No.")
    assert img.size == (1080, 1920)
    assert perto(img.getpixel((60, 810)), (30, 50, 40))
    assert perto(img.getpixel((540, 1600)), PARCH)
    fim = vertical.cartao_final(perg, lousa, FONTE)
    assert fim.size == (1080, 1920) and perto(fim.getpixel((60, 810)), (30, 50, 40))


def test_linha_tempo_vertical(perg):
    base, marcos = vertical.linha_tempo(perg, FONTE, "1775 ride → 1860 poem")
    assert base.size == (1080, 1920) and len(marcos) == 2
    assert perto(marcos[0].getpixel((110, 810)), (179, 38, 30, 255))
    assert perto(marcos[1].getpixel((970, 810)), (179, 38, 30, 255))
    assert all(m.size == (1080, 1920) and m.mode == "RGBA" for m in marcos)


def test_cena_vertical(tmp_path, perg):
    q = []
    for k, cor in enumerate([(255, 0, 0), (0, 255, 0)]):
        Image.new("RGB", (1536, 1024), cor).save(tmp_path / f"q{k}.png")
        q.append(tmp_path / f"q{k}.png")
    quadros = vertical.cena(perg, q)
    assert [f.size for f in quadros] == [(1080, 1920)] * 2
    assert perto(quadros[1].getpixel((540, 810)), (0, 255, 0))
    assert perto(quadros[0].getpixel((540, 200)), PARCH)


@pytest.mark.parametrize("texto", [
    "Why everybody gets Galileo's 'yet it moves' quote completely wrong",
    "Gladiators, pigs and gypsy jugglers: the quirky typography quiz",
    "Marie Antoinette Never Said It?",
    "Qyqgpj really short gypsy yet",
    "typography yet jumping typography myth yet",
    "She never said \"Let them eat cake\" and here is why it matters so much",
])
def test_gancho_tinta_dentro_da_faixa(texto):
    x0, y0, x1, y1 = vertical.gancho(FONTE, texto).getchannel("A").getbbox()
    assert 60 <= x0 and x1 <= 1020 and 110 <= y0 and y1 <= 330


POSE_ALTA = Path(__file__).resolve().parent.parent / "historia" / "mascote" / "poses" / "cetico.webp"


def _topo_troll():
    return vertical.troll(POSE_ALTA)[1][1]


def _tinta(com, sem):
    """Caixa da tinta: onde a imagem com texto difere da sem texto."""
    return ImageChops.difference(com.convert("RGB"), sem.convert("RGB")).getbbox()


def test_lousa_com_troll_fica_acima_do_troll(perg, lousa):
    texto = "Nobody ever said that sentence and the problem here is the whole legend"
    sem = vertical.lousa(perg, lousa, FONTE, "", com_troll=True)
    _, y0, _, y1 = _tinta(vertical.lousa(perg, lousa, FONTE, texto, com_troll=True), sem)
    assert y1 <= _topo_troll() - 10 and y0 >= 500


def test_linha_tempo_com_troll_legendas_acima_do_troll(perg):
    texto = "1775 ride → 1860 poem → 1900 Einstein? → 1950 problem here"
    base, marcos = vertical.linha_tempo(perg, FONTE, texto, com_troll=True)
    vazio = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    _, y0, _, y1 = _tinta(marcos[-1], vazio)
    assert y1 < _topo_troll() - 10 and y0 > 360


def test_cartao_final_com_pergunta(perg, lousa):
    sem = vertical.cartao_final(perg, lousa, FONTE)
    com = vertical.cartao_final(perg, lousa, FONTE, "Which quote should I debunk next?")
    assert com.size == (1080, 1920) and ImageChops.difference(sem, com).getbbox()
    giz = ImageChops.difference(com, vertical.cartao_final(perg, lousa, FONTE, " ")).getbbox()
    assert giz and 40 <= giz[0] and giz[2] <= 1040 and 506 <= giz[1] and giz[3] <= 1114

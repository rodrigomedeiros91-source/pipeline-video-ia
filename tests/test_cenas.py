import base64
from pathlib import Path
from types import SimpleNamespace

import pytest

from fabrica import cenas


class ClienteFalso:
    """Imita client.images.edit da OpenAI e grava os argumentos de cada chamada."""

    def __init__(self, erro=None):
        self.images = self
        self.erro = erro
        self.chamadas = []
        self.arquivos = []

    def edit(self, **kw):
        self.arquivos += kw["image"]
        self.chamadas.append({**kw, "image": [Path(f.name).name for f in kw["image"]]})
        if self.erro:
            raise self.erro
        return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(b"PNGDATA").decode())])


def refs(tmp_path):
    arquivos = [tmp_path / "neutro.webp", tmp_path / "explicando.webp"]
    for a in arquivos:
        a.write_bytes(b"W")
    return arquivos


def test_quadro1(tmp_path):
    c = ClienteFalso()
    destino = tmp_path / "imagens" / "1.2-q1.png"
    cenas.gerar_quadro1(c, "Peasants at the gates", refs(tmp_path), destino)
    assert c.chamadas == [{"model": "gpt-image-2", "image": ["neutro.webp", "explicando.webp"],
                           "prompt": cenas.PREFIXO_ESTILO + "Peasants at the gates",
                           "size": "1536x1024", "quality": "medium"}]
    assert destino.read_bytes() == b"PNGDATA"
    assert all(f.closed for f in c.arquivos)
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.parametrize("n", [2, 3, 4])
def test_pose(tmp_path, n):
    q1 = tmp_path / "1.2-q1.png"
    q1.write_bytes(b"Q1")
    c = ClienteFalso()
    cenas.gerar_pose(c, q1, tmp_path / f"1.2-q{n}.png", n)
    assert c.chamadas == [{"model": "gpt-image-2", "image": ["1.2-q1.png"],
                           "prompt": cenas.PROMPTS_POSES[n], "size": "1536x1024",
                           "quality": "medium"}]
    assert (tmp_path / f"1.2-q{n}.png").read_bytes() == b"PNGDATA"


def test_erro_da_api_nao_grava_e_fecha_arquivos(tmp_path):
    c = ClienteFalso(erro=RuntimeError("recusado"))
    destino = tmp_path / "1.2-q1.png"
    with pytest.raises(RuntimeError):
        cenas.gerar_quadro1(c, "x", refs(tmp_path), destino)
    assert not destino.exists()
    assert all(f.closed for f in c.arquivos)


def test_constantes():
    assert cenas.REFS == ("neutro", "explicando")
    assert cenas.CUSTO_IMAGEM == 0.06
    assert cenas.PREFIXO_ESTILO.endswith("Scene: ")
    assert "no text" in cenas.PREFIXO_ESTILO
    assert cenas.POSES_CENA == 4
    assert sorted(cenas.PROMPTS_POSES) == [2, 3, 4]
    assert all(p.endswith("No new elements.") for p in cenas.PROMPTS_POSES.values())


def test_webp_tem_mime_registrado():
    import mimetypes
    assert mimetypes.guess_type("neutro.webp")[0] == "image/webp"

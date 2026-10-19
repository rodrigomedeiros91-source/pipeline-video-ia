import json

from fabrica import etapa, salvar_json


def test_etapa_gera_e_salva_quando_nao_existe(tmp_path):
    caminho = tmp_path / "x.json"
    chamadas = []

    def gerar():
        chamadas.append(1)
        return {"a": "ção"}

    assert etapa(caminho, gerar) == {"a": "ção"}
    assert json.loads(caminho.read_text("utf-8")) == {"a": "ção"}
    assert etapa(caminho, gerar) == {"a": "ção"}
    assert len(chamadas) == 1  # segunda vez veio do cache


def test_salvar_json_nao_deixa_tmp(tmp_path):
    caminho = tmp_path / "sub" / "y.json"
    salvar_json(caminho, [1, 2])
    assert caminho.exists()
    assert not list(caminho.parent.glob("*.tmp"))

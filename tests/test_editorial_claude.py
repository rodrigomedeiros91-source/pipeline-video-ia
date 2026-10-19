import json
from types import SimpleNamespace

import pytest

from fabrica.editorial import achar_momentos, roteirizar


class ClienteFalso:
    """Imita client.beta.messages.create devolvendo respostas JSON em sequência."""

    def __init__(self, respostas, stop_reason="end_turn"):
        self.respostas = list(respostas)
        self.chamadas = []
        self.stop_reason = stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.chamadas.append(kwargs)
        texto = json.dumps(self.respostas.pop(0))
        return SimpleNamespace(stop_reason=self.stop_reason,
                               content=[SimpleNamespace(type="text", text=texto)])


def narr(n, inicio=100.0):
    return {"tipo": "narracao", "en": " ".join(["word"] * n), "pt": " ".join(["palavra"] * n),
            "inicio": inicio, "fim": 0, "legenda_en": "", "legenda_pt": ""}


def orig(inicio, fim):
    return {"tipo": "original", "en": "", "pt": "", "inicio": inicio, "fim": fim,
            "legenda_en": "x", "legenda_pt": "x"}


PALAVRAS = [{"texto": "Frase.", "inicio": float(t), "fim": t + 0.5} for t in range(0, 300, 10)]
MOMENTO = {"inicio": 100.0, "fim": 160.0, "tema": "guide", "motivo": "m", "score_viral": 90}
META = {"titulo": "T #Shorts", "tiktok_legenda": "t", "hashtags": ["#a"], "produto": "p"}
BOA = {"tema": "guide", "score": 90, "fiel_ao_contexto": True, "alertas": [],
       "en": META, "pt": META,
       "blocos": [narr(60), orig(100, 112), narr(60), orig(120, 132)]}
SO_PT = {**BOA, "blocos": [narr(170)]}          # EN 58.6 s inválido, PT 68 s válido
RUIM = {**BOA, "blocos": [orig(100, 140)]}      # inválido nos dois idiomas


def test_achar_momentos_ordena_e_corta():
    momentos = [{**MOMENTO, "score_viral": s} for s in (50, 95, 70)]
    cliente = ClienteFalso([{"momentos": momentos}])
    r = achar_momentos(cliente, PALAVRAS, n=2)
    assert [m["score_viral"] for m in r] == [95, 70]
    chamada = cliente.chamadas[0]
    assert chamada["fallbacks"] == "default"
    assert chamada["output_config"]["format"]["type"] == "json_schema"
    assert "[100.0] Frase." in chamada["messages"][0]["content"]


def test_roteirizar_valida_de_primeira():
    cliente = ClienteFalso([BOA])
    receita, erros = roteirizar(cliente, PALAVRAS, MOMENTO, "Canal X")
    assert erros == {"en": [], "pt": []} and receita == BOA
    assert len(cliente.chamadas) == 1
    assert "Canal X" in cliente.chamadas[0]["messages"][0]["content"]


def test_roteirizar_tenta_de_novo_quando_os_dois_idiomas_falham():
    cliente = ClienteFalso([RUIM, BOA])
    receita, erros = roteirizar(cliente, PALAVRAS, MOMENTO, "X")
    assert erros == {"en": [], "pt": []} and receita == BOA
    assert "corrija" in cliente.chamadas[1]["messages"][0]["content"]


def test_roteirizar_nao_repete_se_um_idioma_passa():
    cliente = ClienteFalso([SO_PT])
    _, erros = roteirizar(cliente, PALAVRAS, MOMENTO, "X")
    assert len(cliente.chamadas) == 1
    assert erros["pt"] == [] and erros["en"]


def test_roteirizar_desiste_apos_segunda_falha():
    cliente = ClienteFalso([RUIM, RUIM])
    _, erros = roteirizar(cliente, PALAVRAS, MOMENTO, "X")
    assert all(erros.values())


def test_recusa_vira_erro():
    cliente = ClienteFalso([{}], stop_reason="refusal")
    with pytest.raises(RuntimeError, match="recusou"):
        achar_momentos(cliente, PALAVRAS)


def test_resposta_cortada_por_max_tokens():
    cliente = ClienteFalso([{}], stop_reason="max_tokens")
    with pytest.raises(RuntimeError, match="max_tokens"):
        achar_momentos(cliente, PALAVRAS)

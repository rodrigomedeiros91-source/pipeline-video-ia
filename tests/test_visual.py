import json
from types import SimpleNamespace

import pytest

from fabrica import cenas, commons, visual
from tests.test_cenas import ClienteFalso
from tests.test_commons import pagina

CAMPO = {"acervo": "busca", "mapa": "busca", "cena": "cena", "texto": "texto_tela",
         "linha_tempo": "texto_tela"}


class Http:
    """Imita a Commons: toda busca devolve n imagens aprovadas; download devolve bytes."""

    def __init__(self, n=4):
        self.n, self.urls = n, []

    def __call__(self, url):
        self.urls.append(url)
        if url.startswith(commons.API):
            paginas = {str(i): pagina(i, f"File:{i}.jpg") for i in range(1, self.n + 1)}
            return json.dumps({"query": {"pages": paginas}}).encode()
        return b"IMG"

    def buscas(self):
        return [u for u in self.urls if u.startswith(commons.API)]


def proibido(*args, **kw):
    raise AssertionError("não devia acessar a rede")


def t(tipo, texto="", mascote=""):
    v = {"tipo": tipo, "busca": "", "cena": "", "texto_tela": "", "mascote": mascote}
    v[CAMPO[tipo]] = texto
    return {"narracao": "word " * 20, "visual": v}


def rot(**trocas):
    caps = {"1.1": t("acervo", "Marie Antoinette portrait", "cetico"),
            "1.2": t("cena", "Peasants at gates"),
            "1.3": t("mapa", "map of France 1789")} | trocas
    return {"slug": "teste", "intro": [t("texto", "Hi", "neutro")],
            "capitulos": [{"trechos": [caps["1.1"], caps["1.2"], caps["1.3"]]}],
            "outro": [t("linha_tempo", "1789 → 1793")]}


@pytest.fixture
def amb(tmp_path):
    base = tmp_path / "historia"
    poses = base / "mascote" / "poses"
    poses.mkdir(parents=True)
    for p in ("neutro", "explicando", "cetico"):
        (poses / f"{p}.webp").write_bytes(b"W")
    return SimpleNamespace(base=base, poses=poses, pasta=base / "visual" / "teste")


def rodar(amb, roteiro=None, anterior=None, trocar=None, regerar=(), http=None, cliente=None):
    return visual.montar(roteiro or rot(), amb.pasta, amb.poses, anterior or {}, trocar or {},
                         set(regerar), http or Http(), cliente or ClienteFalso())


def por_id(manifesto):
    return {e["id"]: e for e in manifesto["trechos"]}


def test_listar_trechos():
    assert [i for i, _ in visual.listar_trechos(rot())] == ["intro.1", "1.1", "1.2", "1.3", "outro.1"]


def test_montar_completo(amb):
    cliente = ClienteFalso()
    m = rodar(amb, cliente=cliente)
    e = por_id(m)
    assert m["slug"] == "teste" and m["faltas"] == []
    a = e["1.1"]
    assert (a["tipo"], a["busca"], a["escolhida"]) == ("acervo", "Marie Antoinette portrait", "A")
    assert [o["letra"] for o in a["opcoes"]] == ["A", "B", "C", "D"]
    assert a["opcoes"][0] == {"letra": "A", "arquivo": "imagens/1.1-A.jpg", "titulo": "1.jpg",
                              "autor": "Jane Doe", "licenca": "Public domain", "url_licenca": "",
                              "pagina": "https://commons.wikimedia.org/wiki/File:1.jpg"}
    assert (a["mascote"], a["mascote_arquivo"]) == ("cetico", "../../mascote/poses/cetico.webp")
    assert all((amb.pasta / o["arquivo"]).read_bytes() == b"IMG" for o in a["opcoes"])
    assert e["1.2"] == {"id": "1.2", "tipo": "cena", "cena": "Peasants at gates",
                        "quadros": [f"imagens/1.2-q{k}.png" for k in range(1, 5)],
                        "mascote": "", "mascote_arquivo": ""}
    assert e["intro.1"] == {"id": "intro.1", "tipo": "texto", "mascote": "neutro",
                            "mascote_arquivo": "../../mascote/poses/neutro.webp"}
    assert e["outro.1"] == {"id": "outro.1", "tipo": "linha_tempo", "mascote": "",
                            "mascote_arquivo": ""}
    assert e["1.3"]["tipo"] == "mapa" and len(e["1.3"]["opcoes"]) == 4
    q1, *poses = cliente.chamadas
    assert q1["image"] == ["neutro.webp", "explicando.webp"]
    assert q1["prompt"] == cenas.PREFIXO_ESTILO + "Peasants at gates"
    assert all(p["image"] == ["1.2-q1.png"] for p in poses)
    assert [p["prompt"] for p in poses] == [cenas.PROMPTS_POSES[k] for k in (2, 3, 4)]


def test_reaproveita_sem_rede(amb):
    m1 = rodar(amb)
    cliente = ClienteFalso(erro=AssertionError("não devia gerar"))
    m2 = rodar(amb, anterior=por_id(m1), http=proibido, cliente=cliente)
    assert m2 == m1
    assert cliente.chamadas == []


def test_preserva_escolhida(amb):
    anterior = por_id(rodar(amb))
    anterior["1.1"]["escolhida"] = "C"
    assert por_id(rodar(amb, anterior=anterior, http=proibido))["1.1"]["escolhida"] == "C"


def test_trocar_aplica(amb):
    anterior = por_id(rodar(amb))
    m = rodar(amb, anterior=anterior, trocar={"1.1": "B"}, http=proibido)
    assert por_id(m)["1.1"]["escolhida"] == "B"


def test_busca_mudou_refaz_so_aquele_trecho(amb):
    anterior = por_id(rodar(amb))
    http = Http(n=2)
    m = rodar(amb, rot(**{"1.1": t("acervo", "Louis XVI portrait", "cetico")}), anterior, http=http)
    a = por_id(m)["1.1"]
    assert len(http.buscas()) == 1 and len(http.urls) == 3
    assert "Louis+XVI" in http.buscas()[0]
    assert [o["letra"] for o in a["opcoes"]] == ["A", "B"] and a["escolhida"] == "A"
    assert not (amb.pasta / "imagens" / "1.1-C.jpg").exists()


def test_tipo_mudou_apaga_arquivos_antigos(amb):
    anterior = por_id(rodar(amb))
    rodar(amb, rot(**{"1.1": t("texto", "Big number")}), anterior, http=proibido)
    assert not list((amb.pasta / "imagens").glob("1.1-*"))


def test_regerar_cena(amb):
    anterior = por_id(rodar(amb))
    cliente = ClienteFalso()
    rodar(amb, anterior=anterior, regerar={"1.2"}, http=proibido, cliente=cliente)
    assert len(cliente.chamadas) == 4


def test_cena_mudou_refaz(amb):
    anterior = por_id(rodar(amb))
    cliente = ClienteFalso()
    m = rodar(amb, rot(**{"1.2": t("cena", "Queen on balcony")}), anterior, http=proibido,
              cliente=cliente)
    assert len(cliente.chamadas) == 4
    assert cliente.chamadas[0]["prompt"].endswith("Queen on balcony")
    assert por_id(m)["1.2"]["cena"] == "Queen on balcony"


def test_so_quadro2_faltando(amb):
    anterior = por_id(rodar(amb))
    (amb.pasta / "imagens" / "1.2-q2.png").unlink()
    cliente = ClienteFalso()
    rodar(amb, anterior=anterior, http=proibido, cliente=cliente)
    assert [c["prompt"] for c in cliente.chamadas] == [cenas.PROMPTS_POSES[2]]


def test_projeto_antigo_com_2_quadros_gera_so_q3_e_q4(amb):
    imagens = amb.pasta / "imagens"
    imagens.mkdir(parents=True)
    (imagens / "1.2-q1.png").write_bytes(b"Q1")
    (imagens / "1.2-q2.png").write_bytes(b"Q2")
    anterior = {"1.2": {"id": "1.2", "tipo": "cena", "cena": "Peasants at gates",
                        "quadros": ["imagens/1.2-q1.png", "imagens/1.2-q2.png"]}}
    assert visual.cenas_pendentes(rot(), anterior, amb.pasta, set()) == 2
    cliente = ClienteFalso()
    m = rodar(amb, anterior=anterior, cliente=cliente)
    assert [c["prompt"] for c in cliente.chamadas] == [cenas.PROMPTS_POSES[3], cenas.PROMPTS_POSES[4]]
    assert (imagens / "1.2-q1.png").read_bytes() == b"Q1"
    assert (imagens / "1.2-q2.png").read_bytes() == b"Q2"
    assert len(por_id(m)["1.2"]["quadros"]) == 4


def test_erro_na_cena_vira_falta(amb):
    cliente = ClienteFalso(erro=RuntimeError("recusado"))
    m = rodar(amb, cliente=cliente)
    assert len(cliente.chamadas) == 1
    assert por_id(m)["1.2"]["quadros"] == []
    assert m["faltas"] == [{"id": "1.2", "motivo": "erro ao gerar cena: recusado"}]


def test_sem_imagem_livre(amb):
    http = Http(n=0)
    m = rodar(amb, http=http)
    a = por_id(m)["1.1"]
    assert (a["opcoes"], a["escolhida"]) == ([], "")
    assert {"id": "1.1", "motivo": "sem imagem livre para 'Marie Antoinette portrait'"} in m["faltas"]
    assert len(http.buscas()) == 4  # 1.1 e 1.3, cada uma com a repetição sem a última palavra


def test_erro_de_rede_vira_falta(amb):
    def http(url):
        raise OSError("timeout")

    m = rodar(amb, http=http)
    assert m["faltas"] == [{"id": "1.1", "motivo": "erro na Commons: timeout"},
                           {"id": "1.3", "motivo": "erro na Commons: timeout"}]
    assert por_id(m)["1.1"]["opcoes"] == []


def test_pose_ausente_vira_falta(amb):
    m = rodar(amb, rot(**{"1.3": t("mapa", "map of France 1789", "rindo")}))
    e = por_id(m)["1.3"]
    assert (e["mascote"], e["mascote_arquivo"]) == ("rindo", "")
    assert m["faltas"] == [{"id": "1.3", "motivo": "pose 'rindo' não encontrada"}]


def test_cenas_pendentes(amb):
    assert visual.cenas_pendentes(rot(), {}, amb.pasta, set()) == 4
    anterior = por_id(rodar(amb))
    assert visual.cenas_pendentes(rot(), anterior, amb.pasta, set()) == 0
    assert visual.cenas_pendentes(rot(), anterior, amb.pasta, {"1.2"}) == 4
    novo = rot(**{"1.2": t("cena", "Queen on balcony")})
    assert visual.cenas_pendentes(novo, anterior, amb.pasta, set()) == 4
    (amb.pasta / "imagens" / "1.2-q4.png").unlink()
    assert visual.cenas_pendentes(rot(), anterior, amb.pasta, set()) == 1


def test_ids_fora_do_roteiro_sao_apagados(amb):
    m1 = rodar(amb)
    (amb.pasta / "imagens" / "2.9-q1.png").write_bytes(b"X")
    m2 = rodar(amb, anterior=por_id(m1), http=proibido, cliente=ClienteFalso(erro=AssertionError("não devia")))
    assert not (amb.pasta / "imagens" / "2.9-q1.png").exists()
    assert m2["faltas"] == []
    assert (amb.pasta / "imagens" / "1.1-A.jpg").exists()


def test_quadro1_faltando_regera_todos(amb):
    rodar(amb)
    anterior = por_id(rodar(amb))
    (amb.pasta / "imagens" / "1.2-q1.png").unlink()
    assert visual.cenas_pendentes(rot(), anterior, amb.pasta, set()) == 4
    cliente = ClienteFalso()
    rodar(amb, anterior=anterior, http=proibido, cliente=cliente)
    assert len(cliente.chamadas) == 4
    assert cliente.chamadas[0]["prompt"] == cenas.PREFIXO_ESTILO + "Peasants at gates"
    assert [c["prompt"] for c in cliente.chamadas[1:]] == [cenas.PROMPTS_POSES[k] for k in (2, 3, 4)]


def test_resposta_truncada_vira_falta(amb):
    from http.client import IncompleteRead

    def http(url):
        raise IncompleteRead(b"")

    m = rodar(amb, http=http)
    assert [f["id"] for f in m["faltas"]] == ["1.1", "1.3"]
    assert all(f["motivo"].startswith("erro na Commons: ") for f in m["faltas"])

import json
from types import SimpleNamespace

import pytest

from fabrica import visual
from tests.test_cenas import ClienteFalso
from tests.test_roteiro import roteiro
from tests.test_visual import Http, proibido


def op(letra, pagina, url_lic=""):
    return {"letra": letra, "arquivo": f"imagens/x-{letra}.jpg", "titulo": f"T{letra}",
            "autor": "Ana", "licenca": "CC BY 4.0", "url_licenca": url_lic, "pagina": pagina}


def entrada(id_, tipo, **kw):
    return {"id": id_, "tipo": tipo, "mascote": "", "mascote_arquivo": ""} | kw


MANIFESTO = {"slug": "s", "faltas": [{"id": "1.5", "motivo": "sem imagem livre para 'w'"}],
             "trechos": [
                 entrada("1.1", "acervo", busca="b", escolhida="B",
                         opcoes=[op("A", "p1"), op("B", "p2", "https://cc/by4")]),
                 entrada("1.2", "cena", cena="c", quadros=[f"imagens/1.2-q{k}.png" for k in range(1, 5)]),
                 entrada("1.3", "mapa", busca="m", escolhida="A",
                         opcoes=[op("A", "p2", "https://cc/by4")]),
                 entrada("1.4", "acervo", busca="z", escolhida="A", opcoes=[op("A", "p3")],
                         mascote="cetico", mascote_arquivo="../../mascote/poses/cetico.webp"),
                 entrada("1.5", "acervo", busca="w", escolhida="", opcoes=[])]}


def test_creditos():
    assert visual.creditos(MANIFESTO) == (
        "Images from Wikimedia Commons:\n"
        '- "TB" by Ana, CC BY 4.0 (https://cc/by4) — p2\n'
        '- "TA" by Ana, CC BY 4.0 — p3\n'
        "\n"
        "Illustrations and mascot: original artwork for this channel.\n")


def test_revisao():
    narracoes = {"1.1": "Hollywood loves <script>alert(1)</script> drama " + "word " * 20}
    pagina = visual.revisao(MANIFESTO, narracoes)
    for id_ in ("1.1", "1.2", "1.3", "1.4", "1.5"):
        assert f"<h2>{id_} · " in pagina
    assert "<script>" not in pagina and "&lt;script&gt;" in pagina
    assert "<p>5 trechos, 1 faltas</p>" in pagina
    assert "class='trecho falta'" in pagina
    assert "sem imagem livre para &#x27;w&#x27;" in pagina
    assert "<img src='imagens/x-B.jpg' width='480'>" in pagina
    assert "<img src='imagens/x-A.jpg' width='240'>" in pagina
    assert "<img src='imagens/1.2-q2.png' width='480'>" in pagina
    assert "<img src='../../mascote/poses/cetico.webp' width='120'>" in pagina
    assert "--trocar 3.4=B" in pagina and "--regerar 5.1" in pagina


@pytest.fixture
def cli(tmp_path, monkeypatch):
    base = tmp_path / "historia"
    (base / "roteiros").mkdir(parents=True)
    (base / "roteiros" / "roman-myths.json").write_text(json.dumps(roteiro()), "utf-8")
    poses = base / "mascote" / "poses"
    poses.mkdir(parents=True)
    for p in ("neutro", "explicando"):
        (poses / f"{p}.webp").write_bytes(b"W")
    monkeypatch.setenv("OPENAI_API_KEY", "teste")
    pasta = base / "visual" / "roman-myths"

    def rodar(*args, http=None, cliente=None):
        c = cliente or ClienteFalso()
        return visual.main(["roman-myths", *args], base=base, http=http or Http(),
                           criar_cliente=lambda: c)

    return SimpleNamespace(base=base, pasta=pasta, rodar=rodar)


def ler(cli):
    return {e["id"]: e for e in json.loads((cli.pasta / "manifesto.json").read_text("utf-8"))["trechos"]}


def test_main_gera_tudo(cli, capsys):
    cliente = ClienteFalso()
    assert cli.rodar(cliente=cliente) == 0
    assert len(cliente.chamadas) == 24
    for nome in ("manifesto.json", "creditos.txt", "revisao.html"):
        assert (cli.pasta / nome).exists()
    assert "24 imagens a gerar (~US$ 1.44)" in capsys.readouterr().out


def test_main_sem_chave(cli, monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY")
    assert cli.rodar(http=proibido) == 2
    assert "OPENAI_API_KEY" in capsys.readouterr().out
    assert not (cli.pasta / "manifesto.json").exists()


def test_main_sem_cenas_pendentes_nao_exige_chave(cli, monkeypatch):
    assert cli.rodar() == 0
    monkeypatch.delenv("OPENAI_API_KEY")
    assert cli.rodar(http=proibido, cliente=ClienteFalso(erro=AssertionError("não devia"))) == 0


def test_main_roteiro_inexistente(cli):
    assert visual.main(["nao-existe"], base=cli.base, http=proibido, criar_cliente=proibido) == 2


def test_main_roteiro_invalido(cli, capsys):
    (cli.base / "roteiros" / "roman-myths.json").write_text('{"slug": "roman-myths"}', "utf-8")
    assert cli.rodar(http=proibido) == 2
    assert "roteiro inválido" in capsys.readouterr().out


def test_main_trocar_valido(cli):
    cli.rodar()
    assert cli.rodar("--trocar", "1.2=B", http=proibido) == 0
    assert ler(cli)["1.2"]["escolhida"] == "B"


def test_main_trocar_invalido_nao_altera(cli, capsys):
    cli.rodar()
    antes = (cli.pasta / "manifesto.json").read_bytes()
    assert cli.rodar("--trocar", "1.2=E", http=proibido) == 2
    assert "1.2" in capsys.readouterr().out
    assert (cli.pasta / "manifesto.json").read_bytes() == antes


def test_main_regerar_cena(cli):
    cli.rodar()
    cliente = ClienteFalso()
    assert cli.rodar("--regerar", "1.1", http=proibido, cliente=cliente) == 0
    assert len(cliente.chamadas) == 4


def test_main_regerar_nao_cena(cli):
    cli.rodar()
    assert cli.rodar("--regerar", "1.2", http=proibido) == 2


def test_main_faltas_retorna_1(cli, capsys):
    assert cli.rodar(http=Http(n=0)) == 1
    assert "sem imagem livre" in capsys.readouterr().out


def test_main_slug_diferente_do_arquivo(cli, capsys):
    r = roteiro()
    r["slug"] = "outro-slug"
    (cli.base / "roteiros" / "roman-myths.json").write_text(json.dumps(r), "utf-8")
    assert cli.rodar(http=proibido) == 2
    assert "outro-slug" in capsys.readouterr().out
    assert not (cli.pasta / "manifesto.json").exists()

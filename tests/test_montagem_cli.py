import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from fabrica import montagem

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg ausente")

FONTE = Path(__file__).resolve().parent.parent / "historia" / "fontes" / "PatrickHand-Regular.ttf"
CAMPO = {"acervo": "busca", "mapa": "busca", "cena": "cena", "texto": "texto_tela",
         "linha_tempo": "texto_tela"}


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def trecho(tipo, texto="x", mascote=""):
    v = {"tipo": tipo, "busca": "", "cena": "", "texto_tela": "", "mascote": mascote}
    v[CAMPO[tipo]] = texto
    return {"narracao": "one two three", "visual": v}


ROTEIRO = {
    "slug": "teste", "titulo": "Test Video", "descricao_youtube": "A test.",
    "tags": ["history", "test"],
    "intro": [trecho("acervo", "x", "neutro")],
    "capitulos": [{"titulo": "First Myth",
                   "short": {"titulo": "First #Shorts", "hashtags": ["#a", "#b"]},
                   "trechos": [trecho("cena", "A scene"), trecho("texto", "Big text", "neutro"),
                               trecho("linha_tempo", "1775 ride → 1860 poem", "neutro")],
                   "fontes": [{"afirmacao": "a", "url": "https://example.org/a"}]}],
    "outro": [trecho("mapa")],
    "alertas": [],
}


def opcao(arquivo):
    return {"letra": "A", "arquivo": arquivo, "titulo": "T", "autor": "Ana", "licenca": "CC0",
            "url_licenca": "", "pagina": "https://commons.wikimedia.org/wiki/File:T.jpg"}


@pytest.fixture
def amb(tmp_path, monkeypatch):
    base = tmp_path / "historia"
    (base / "roteiros").mkdir(parents=True)
    (base / "roteiros" / "teste.json").write_text(json.dumps(ROTEIRO), "utf-8")
    vis = base / "visual" / "teste"
    (vis / "imagens").mkdir(parents=True)
    for nome, cor, tam in (("intro.1-A.jpg", "blue", (800, 600)), ("outro.1-A.jpg", "green", (600, 800)),
                           ("1.1-q1.png", "red", (1536, 1024)), ("1.1-q2.png", "orange", (1536, 1024))):
        Image.new("RGB", tam, cor).save(vis / "imagens" / nome)
    pose = "../../mascote/poses/neutro.webp"
    manifesto = {"slug": "teste", "faltas": [], "trechos": [
        {"id": "intro.1", "tipo": "acervo", "busca": "x", "escolhida": "A",
         "opcoes": [opcao("imagens/intro.1-A.jpg")], "mascote": "neutro", "mascote_arquivo": pose},
        {"id": "1.1", "tipo": "cena", "cena": "A scene",
         "quadros": ["imagens/1.1-q1.png", "imagens/1.1-q2.png"], "mascote": "", "mascote_arquivo": ""},
        {"id": "1.2", "tipo": "texto", "mascote": "neutro", "mascote_arquivo": pose},
        {"id": "1.3", "tipo": "linha_tempo", "mascote": "neutro", "mascote_arquivo": pose},
        {"id": "outro.1", "tipo": "mapa", "busca": "x", "escolhida": "A",
         "opcoes": [opcao("imagens/outro.1-A.jpg")], "mascote": "", "mascote_arquivo": ""},
    ]}
    (vis / "manifesto.json").write_text(json.dumps(manifesto), "utf-8")
    (vis / "creditos.txt").write_text("Images from Wikimedia Commons:\n- \"T\" by Ana, CC0 — https://x\n",
                                      "utf-8")
    poses = base / "mascote" / "poses"
    poses.mkdir(parents=True)
    troll = Image.new("RGBA", (300, 400), (0, 0, 0, 0))
    troll.paste((200, 120, 60, 255), (50, 50, 250, 350))
    for p in ("neutro", "apontando"):
        troll.save(poses / f"{p}.webp", lossless=True)
    (base / "fontes").mkdir()
    shutil.copy(FONTE, base / "fontes" / FONTE.name)
    (base / "estilo").mkdir()
    Image.new("RGB", (64, 36), (233, 220, 192)).save(base / "estilo" / "pergaminho.png")
    objetos = base / "estilo" / "objetos"
    objetos.mkdir()
    Image.new("RGBA", (140, 85), (30, 50, 40, 255)).save(objetos / "lousa.png")
    Image.new("RGBA", (135, 93), (240, 225, 190, 255)).save(objetos / "pergaminho.png")
    (base / "musica").mkdir()
    ff("-f", "lavfi", "-i", "sine=frequency=330:duration=6", str(base / "musica" / "a.mp3"))

    monkeypatch.setenv("ELEVENLABS_VOZ_HISTORIA", "voz-teste")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "chave-teste")
    monkeypatch.setattr(montagem, "validar_roteiro", lambda dados: [])
    chamadas = []

    def narrar(cliente, texto, destino, voice_id, idioma):
        chamadas.append(texto)
        palavras = texto.split()
        destino.parent.mkdir(parents=True, exist_ok=True)
        ff("-f", "lavfi", "-i", f"sine=frequency=440:duration={len(palavras) * 0.25 + 0.2:.2f}",
           str(destino))
        return [{"texto": w, "inicio": i * 0.25, "fim": i * 0.25 + 0.2} for i, w in enumerate(palavras)]

    monkeypatch.setattr(montagem.audio, "narrar", narrar)
    return SimpleNamespace(base=base, vis=vis, chamadas=chamadas)


def rodar(amb, slug="teste", criar_cliente=lambda: object(), musica=""):
    argv = [slug, "--musica", musica] if musica else [slug]
    return montagem.main(argv, base=amb.base, criar_cliente=criar_cliente)


def ffprobe(*args):
    return subprocess.run(["ffprobe", "-v", "error", *args], capture_output=True, text=True,
                          check=True).stdout.split()


def test_monta_o_video_completo(amb):
    assert rodar(amb) == 0
    saida = amb.base / "videos" / "teste"
    video = str(saida / "video.mp4")
    assert ffprobe("-show_entries", "stream=codec_type", "-of", "csv=p=0", video) == ["video", "audio"]
    caps = json.loads((saida / "capitulos.json").read_text("utf-8"))
    assert [c["id"] for c in caps] == ["intro", "1", "outro"]
    assert caps[1]["short"]["titulo"] == "First #Shorts"
    dur = float(ffprobe("-show_entries", "format=duration", "-of", "csv=p=0", video)[0])
    assert abs(dur - caps[-1]["fim"]) < 0.2
    desc = (saida / "descricao.txt").read_text("utf-8")
    for trecho_esperado in ("TITLE: Test Video", "0:00 Intro", "#1 First Myth",
                            "- https://example.org/a", "TAGS: history, test"):
        assert trecho_esperado in desc
    assert (saida / "legendas.srt").read_text("utf-8").startswith("1\n00:00:00,000 --> ")
    assert len(amb.chamadas) == 3


def test_segunda_rodada_reaproveita_tudo(amb, capsys, monkeypatch):
    assert rodar(amb) == 0
    capsys.readouterr()
    monkeypatch.delenv("ELEVENLABS_API_KEY")

    def proibido(*args, **kw):
        raise AssertionError("não devia narrar")

    monkeypatch.setattr(montagem.audio, "narrar", proibido)
    assert rodar(amb, criar_cliente=proibido) == 0
    assert "(0 gerados, 6 reaproveitados)" in capsys.readouterr().out


def test_faltas_no_manifesto(amb, capsys):
    m = json.loads((amb.vis / "manifesto.json").read_text("utf-8"))
    m["faltas"] = [{"id": "1.1", "motivo": "x"}]
    (amb.vis / "manifesto.json").write_text(json.dumps(m), "utf-8")
    assert rodar(amb) == 2
    assert "faltas" in capsys.readouterr().out and amb.chamadas == []


def test_manifesto_desatualizado(amb, capsys):
    m = json.loads((amb.vis / "manifesto.json").read_text("utf-8"))
    m["trechos"] = m["trechos"][:-1]
    (amb.vis / "manifesto.json").write_text(json.dumps(m), "utf-8")
    assert rodar(amb) == 2
    assert "fabrica.visual" in capsys.readouterr().out


def test_arquivo_do_manifesto_ausente(amb, capsys):
    (amb.vis / "imagens" / "1.1-q2.png").unlink()
    assert rodar(amb) == 2
    assert "1.1-q2.png" in capsys.readouterr().out


def test_sem_musica(amb, capsys):
    (amb.base / "musica" / "a.mp3").unlink()
    assert rodar(amb) == 2
    assert "música" in capsys.readouterr().out


def test_musica_invalida(amb, capsys):
    ff("-f", "lavfi", "-i", "sine=frequency=330:duration=2", str(amb.base / "musica" / "b.mp3"))
    assert rodar(amb) == 2
    assert "música inválida" in capsys.readouterr().out


def test_musica_inexistente(amb, capsys):
    assert rodar(amb, musica="nao-existe") == 2
    assert "nenhuma música em historia/musica/ contém 'nao-existe'" in capsys.readouterr().out
    assert amb.chamadas == []


def test_musica_escolhida(amb):
    assert rodar(amb, musica="A") == 0


def test_objeto_ausente(amb, capsys):
    (amb.base / "estilo" / "objetos" / "lousa.png").unlink()
    assert rodar(amb) == 2
    assert "lousa.png" in capsys.readouterr().out


def test_sem_voz(amb, monkeypatch, capsys):
    monkeypatch.delenv("ELEVENLABS_VOZ_HISTORIA")
    assert rodar(amb) == 2
    assert "ELEVENLABS_VOZ_HISTORIA" in capsys.readouterr().out


def test_sem_chave_com_narracao_pendente(amb, monkeypatch, capsys):
    monkeypatch.delenv("ELEVENLABS_API_KEY")
    assert rodar(amb) == 2
    assert "ELEVENLABS_API_KEY" in capsys.readouterr().out and amb.chamadas == []


def test_roteiro_inexistente(amb):
    assert rodar(amb, slug="nao-existe") == 2


def test_erro_na_narracao_sai_com_1(amb, monkeypatch, capsys):
    def falha(*args, **kw):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(montagem.audio, "narrar", falha)
    assert rodar(amb) == 1
    assert "quota exceeded" in capsys.readouterr().out

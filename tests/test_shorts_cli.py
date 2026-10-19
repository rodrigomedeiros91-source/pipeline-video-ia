import json
import shutil
import subprocess

import pytest
from PIL import Image

from fabrica import montagem, shorts
from tests.test_montagem_cli import amb  # noqa: F401 (fixture)

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg ausente")


def ffprobe(*args):
    return subprocess.run(["ffprobe", "-v", "error", *args], capture_output=True, text=True,
                          check=True).stdout.split()


@pytest.fixture
def montado(amb):
    assert montagem.main(["teste"], base=amb.base, criar_cliente=lambda: object()) == 0
    return amb


def rodar(amb, *args):
    return shorts.main(["teste", *args], base=amb.base, hoje=__import__("datetime").date(2026, 10, 5))


def test_gera_short_e_pacote(montado):
    assert rodar(montado) == 0
    pasta = montado.base / "shorts" / "teste"
    video = str(pasta / "short-1.mp4")
    assert ffprobe("-show_entries", "stream=codec_type", "-of", "csv=p=0", video) == ["video", "audio"]
    assert ffprobe("-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                   video) == ["1080,1920"]
    caps = json.loads((montado.base / "videos" / "teste" / "capitulos.json").read_text("utf-8"))
    esperado = caps[1]["fim"] - caps[1]["inicio_narracao"] + shorts.FIM
    dur = float(ffprobe("-show_entries", "format=duration", "-of", "csv=p=0", video)[0])
    assert abs(dur - esperado) < 0.2
    pac = json.loads((pasta / "publicacao.json").read_text("utf-8"))
    assert pac["longo"]["data"] == "2026-10-10" and pac["shorts"][0]["data"] == "2026-10-10"
    assert pac["shorts"][0]["titulo"] == "First #Shorts"
    assert "Short 1: First #Shorts" in (pasta / "calendario.md").read_text("utf-8")


def test_legenda_gravada(montado, tmp_path):
    assert rodar(montado) == 0
    video = montado.base / "shorts" / "teste" / "short-1.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "0.3", "-i", str(video), "-frames:v", "1",
                    str(tmp_path / "q.png")], check=True)
    faixa = Image.open(tmp_path / "q.png").convert("RGB").crop((60, 1430, 1020, 1600))
    brancos = sum(1 for px in zip(*[iter(faixa.tobytes())] * 3) if min(px) > 235)
    assert brancos > 300


def test_rodar_de_novo_preserva_agendamento(montado):
    assert rodar(montado) == 0
    arq = montado.base / "shorts" / "teste" / "publicacao.json"
    pac = json.loads(arq.read_text("utf-8"))
    pac["longo"] |= {"status": "agendado", "url": "https://youtu.be/L"}
    arq.write_text(json.dumps(pac), "utf-8")
    assert rodar(montado, "--inicio", "2026-11-07") == 0
    novo = json.loads(arq.read_text("utf-8"))
    assert novo["longo"]["status"] == "agendado" and novo["longo"]["data"] == "2026-10-10"
    assert novo["shorts"][0]["data"] == "2026-11-07"
    assert "https://youtu.be/L" in novo["shorts"][0]["descricao_youtube"]


def test_sem_montagem(amb, capsys):
    assert rodar(amb) == 2
    assert "fabrica.montagem" in capsys.readouterr().out


def test_inicio_invalido(montado, capsys):
    assert rodar(montado, "--inicio", "10/10/2026") == 2
    assert "--inicio" in capsys.readouterr().out


def test_musica_inexistente(montado, capsys):
    assert rodar(montado, "--musica", "nao-existe") == 2
    assert "nenhuma música" in capsys.readouterr().out


def test_short_curto_com_falas(montado):
    r = json.loads((montado.base / "roteiros" / "teste.json").read_text("utf-8"))
    r["capitulos"][0]["short"] |= {"trechos": [1, 3], "abertura": "This is fake.", "pergunta": "Why though?"}
    (montado.base / "roteiros" / "teste.json").write_text(json.dumps(r), "utf-8")
    assert rodar(montado) == 0
    assert "This is fake." in montado.chamadas and "Why though?" in montado.chamadas
    video = str(montado.base / "shorts" / "teste" / "short-1.mp4")
    dur = float(ffprobe("-show_entries", "format=duration", "-of", "csv=p=0", video)[0])
    # abertura 0,95 + trecho 1 (0,725) + trecho 3 (~0,98) + pergunta 0,7 + cartão 3
    assert abs(dur - 6.35) < 0.3
    assert rodar(montado) == 0 and montado.chamadas.count("This is fake.") == 1  # falas ficam em cache

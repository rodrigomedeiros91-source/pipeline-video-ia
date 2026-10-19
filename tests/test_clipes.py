import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from fabrica import clipes

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg ausente")


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def png(caminho, cor, tamanho=(1920, 1080), modo="RGB"):
    Image.new(modo, tamanho, cor).save(caminho)
    return caminho


def probe(caminho):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,avg_frame_rate,nb_frames", "-of", "csv=p=0",
                        str(caminho)], capture_output=True, text=True, check=True)
    return r.stdout.strip()


def tipos(caminho):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of",
                        "csv=p=0", str(caminho)], capture_output=True, text=True, check=True)
    return r.stdout.split()


def quadro_em(video, t, destino):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1",
                    str(destino)], check=True)
    return Image.open(destino).convert("RGB")


@pytest.fixture
def troll(tmp_path):
    return {"arquivo": str(png(tmp_path / "troll.png", (200, 120, 60, 255), (200, 300), "RGBA")),
            "x": 1600, "y": 700}


def test_clipe_zoom_com_troll(tmp_path, troll):
    r = {"modo": "zoom", "quadros": 30, "fundo": str(png(tmp_path / "f.png", "blue")), "troll": troll}
    clipes.render_clipe(r, tmp_path / "c.mp4")
    assert probe(tmp_path / "c.mp4") == "1920,1080,30/1,30"
    assert not list(tmp_path.glob("*.tmp.*"))


def test_clipe_fixo_sem_troll(tmp_path):
    r = {"modo": "fixo", "quadros": 15, "fundo": str(png(tmp_path / "f.png", "white")), "troll": None}
    clipes.render_clipe(r, tmp_path / "c.mp4")
    assert probe(tmp_path / "c.mp4") == "1920,1080,30/1,15"


def test_clipe_marcos(tmp_path, troll):
    marcos = [str(png(tmp_path / f"m{k}.png", (255, 0, 0, 255), modo="RGBA")) for k in range(2)]
    r = {"modo": "marcos", "quadros": 30, "fundo": str(png(tmp_path / "f.png", "white")),
         "marcos": marcos, "troll": troll}
    clipes.render_clipe(r, tmp_path / "c.mp4")
    assert probe(tmp_path / "c.mp4") == "1920,1080,30/1,30"


@pytest.mark.parametrize("n", [1, 2])
def test_clipe_cena(tmp_path, n):
    cena = [str(png(tmp_path / f"q{k}.png", c, (1536, 1024))) for k, c in enumerate(["red", "green"][:n])]
    clipes.render_clipe({"modo": "cena", "quadros": 30, "cena": cena, "troll": None}, tmp_path / "c.mp4")
    assert probe(tmp_path / "c.mp4") == "1920,1080,30/1,30"


def test_janelas_poses():
    janelas, ciclo = clipes.janelas_poses(4)
    assert ciclo == 6.4
    assert janelas == {2: [(1.2, 1.45), (1.7, 1.95), (4.5, 4.75), (5.0, 5.25)],
                       3: [(2.55, 2.7), (5.85, 6.0)],
                       4: [(3.5, 4.5), (4.75, 5.0), (5.25, 5.85), (6.0, 6.4)]}
    assert list(clipes.janelas_poses(2)[0]) == [2]
    assert clipes.janelas_poses(1) == ({}, 6.4)


def test_clipe_cena_quatro_quadros_com_pan(tmp_path):
    cena = [str(png(tmp_path / f"q{k}.png", c, (1536, 1024)))
            for k, c in enumerate(["red", "green", "blue", "yellow"])]
    clipes.render_clipe({"modo": "cena", "quadros": 30, "cena": cena, "pan": 1, "troll": None},
                        tmp_path / "c.mp4")
    assert probe(tmp_path / "c.mp4") == "1920,1080,30/1,30"


def test_concatenar(tmp_path):
    partes = []
    for k in range(2):
        r = {"modo": "fixo", "quadros": 15, "fundo": str(png(tmp_path / f"f{k}.png", "white")),
             "troll": None}
        clipes.render_clipe(r, tmp_path / f"c{k}.mp4")
        partes.append(tmp_path / f"c{k}.mp4")
    clipes.concatenar(partes, tmp_path / "junto.mp4")
    assert probe(tmp_path / "junto.mp4") == "1920,1080,30/1,30"


def test_faixa_narracao_com_silencio(tmp_path):
    ff("-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(tmp_path / "a.mp3"))
    clipes.para_wav(tmp_path / "a.mp3", tmp_path / "a.wav")
    clipes.faixa_narracao([tmp_path / "a.wav", 2.0, tmp_path / "a.wav"], tmp_path / "n.wav")
    assert abs(clipes.duracao(tmp_path / "n.wav") - 2 * clipes.duracao(tmp_path / "a.wav") - 2.0) < 0.01


def test_playlist_cobre_e_e_deterministica():
    fs = [Path("c.mp3"), Path("a.mp3"), Path("b.mp3")]
    durs = {f: 100.0 for f in fs}
    curta = clipes.playlist(fs, "slug-x", 250, durs)
    assert curta == clipes.playlist(list(reversed(fs)), "slug-x", 250, durs)
    assert len(curta) == 3 and sorted(curta) == sorted(fs)
    longa = clipes.playlist(fs, "slug-x", 500, durs)
    assert len(longa) == 6 and longa[:3] == curta and longa[3:] == curta


def test_mixar_e_juntar(tmp_path):
    ff("-f", "lavfi", "-i", "sine=frequency=440:duration=4", "-ar", "48000", "-ac", "2",
       str(tmp_path / "n.wav"))
    musicas = []
    for k in range(2):
        ff("-f", "lavfi", "-i", f"sine=frequency={300 + 100 * k}:duration=5", str(tmp_path / f"m{k}.mp3"))
        musicas.append(tmp_path / f"m{k}.mp3")
    clipes.mixar(tmp_path / "n.wav", musicas, 4.0, tmp_path / "mix.m4a")
    assert abs(clipes.duracao(tmp_path / "mix.m4a") - 4.0) < 0.15
    r = {"modo": "fixo", "quadros": 120, "fundo": str(png(tmp_path / "f.png", "white")), "troll": None}
    clipes.render_clipe(r, tmp_path / "v.mp4")
    clipes.juntar(tmp_path / "v.mp4", tmp_path / "mix.m4a", tmp_path / "final.mp4")
    assert tipos(tmp_path / "final.mp4") == ["video", "audio"]


@pytest.mark.parametrize("durs", [{}, {Path("a.mp3"): 3.0}])
def test_playlist_recusa_vazia_ou_curta(durs):
    with pytest.raises(ValueError):
        clipes.playlist(list(durs), "s", 10.0, durs)


def test_concatenar_caminho_com_apostrofo(tmp_path):
    pasta = tmp_path / "it's"
    pasta.mkdir()
    r = {"modo": "fixo", "quadros": 15, "fundo": str(png(tmp_path / "f.png", "white")), "troll": None}
    clipes.render_clipe(r, pasta / "c0.mp4")
    clipes.concatenar([pasta / "c0.mp4"], tmp_path / "junto.mp4")
    assert probe(tmp_path / "junto.mp4") == "1920,1080,30/1,15"


def test_clipe_vertical_com_topo_parado(tmp_path, troll):
    fundo = png(tmp_path / "f.png", "white", (1080, 1920))
    topo = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    topo.paste((200, 0, 0, 255), (0, 150, 1080, 290))
    topo.save(tmp_path / "topo.png")
    r = {"modo": "zoom", "quadros": 30, "fundo": str(fundo), "tamanho": (1080, 1920),
         "topo": str(tmp_path / "topo.png"), "troll": {**troll, "x": 700, "y": 1000}}
    clipes.render_clipe(r, tmp_path / "c.mp4")
    assert probe(tmp_path / "c.mp4") == "1080,1920,30/1,30"
    for t in (0.0, 0.9):
        r_, g, b = quadro_em(tmp_path / "c.mp4", t, tmp_path / f"q{t}.png").getpixel((540, 220))
        assert r_ > 150 and g < 60 and b < 60


def test_clipe_cena_vertical(tmp_path):
    cena = [str(png(tmp_path / f"q{k}.png", c, (1080, 1920))) for k, c in enumerate(["red", "green"])]
    r = {"modo": "cena", "quadros": 30, "cena": cena, "pan": -1, "tamanho": (1080, 1920), "troll": None}
    clipes.render_clipe(r, tmp_path / "c.mp4")
    assert probe(tmp_path / "c.mp4") == "1080,1920,30/1,30"


def test_faixa_narracao_com_recortes(tmp_path):
    ff("-f", "lavfi", "-i", "sine=frequency=440:duration=3", str(tmp_path / "a.mp3"))
    clipes.para_wav(tmp_path / "a.mp3", tmp_path / "a.wav")
    clipes.faixa_narracao([(tmp_path / "a.wav", 0.5, 1.25), (tmp_path / "a.wav", 2.0, 3.0), 0.5], tmp_path / "n.wav")
    assert abs(clipes.duracao(tmp_path / "n.wav") - 2.25) < 0.02


def video_teste(caminho, segundos=1):
    ff("-f", "lavfi", "-i", f"color=c=red:s=640x360:d={segundos}:r=24", "-pix_fmt", "yuv420p", str(caminho))
    return str(caminho)


def test_clipe_video_animado_cobre_evento_mais_longo(tmp_path):
    # clipe de 1 s num evento de 3 s: fica mais lento e congela no último quadro até completar
    r = {"modo": "video", "quadros": 90, "video": video_teste(tmp_path / "a.mp4"), "duracao": 1.0, "troll": None}
    clipes.render_clipe(r, tmp_path / "c.mp4")
    assert probe(tmp_path / "c.mp4") == "1920,1080,30/1,90"
    r_, g, b = quadro_em(tmp_path / "c.mp4", 2.8, tmp_path / "q.png").getpixel((960, 540))
    assert r_ > 150 and g < 60


def test_clipe_video_animado_vertical_sobre_fundo(tmp_path):
    r = {"modo": "video", "quadros": 30, "video": video_teste(tmp_path / "a.mp4"), "duracao": 1.0,
         "fundo": str(png(tmp_path / "f.png", "blue", (1080, 1920))), "y": 810, "tamanho": (1080, 1920),
         "troll": None}
    clipes.render_clipe(r, tmp_path / "c.mp4")
    assert probe(tmp_path / "c.mp4") == "1080,1920,30/1,30"
    quadro = quadro_em(tmp_path / "c.mp4", 0.5, tmp_path / "q.png")
    assert quadro.getpixel((540, 810))[0] > 150  # vídeo no centro
    assert quadro.getpixel((540, 100))[2] > 150  # pergaminho (azul no teste) em cima

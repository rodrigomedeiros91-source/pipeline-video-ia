import shutil
import subprocess

import pytest

from fabrica.render import duracao, render_short

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg ausente")


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def test_render_short_bilingue_tela_cheia(tmp_path):
    video = tmp_path / "fonte.mp4"
    ff("-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30", "-f", "lavfi",
       "-i", "sine=frequency=440", "-t", "20", "-c:v", "libx264", "-c:a", "aac", str(video))
    narr = tmp_path / "narr.mp3"
    ff("-f", "lavfi", "-i", "sine=frequency=660", "-t", "2", str(narr))

    receita = {"blocos": [
        {"tipo": "narracao", "en": "Hi", "pt": "Olá", "inicio": 5.0, "fim": 0,
         "legenda_en": "", "legenda_pt": ""},
        {"tipo": "original", "en": "", "pt": "", "inicio": 2.0, "fim": 6.0,
         "legenda_en": "test words here", "legenda_pt": "palavras de teste"},
        # 19.5 s + 2 s passa do fim da fonte (20 s): o início deve recuar para caber
        {"tipo": "narracao", "en": "End", "pt": "Fim", "inicio": 19.5, "fim": 0,
         "legenda_en": "", "legenda_pt": ""},
    ]}
    pal_narr = [{"texto": "Olá", "inicio": 0.0, "fim": 0.5}]
    narracoes = [(narr, pal_narr), (narr, pal_narr)]
    palavras = [{"texto": "test", "inicio": 2.5, "fim": 3.0}]
    saida = tmp_path / "out" / "short.mp4"

    render_short(video, receita, "pt", "en", narracoes, palavras, tmp_path / "segs", saida,
                 "Fonte: X")

    dims = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0", str(saida)],
        capture_output=True, text=True, check=True).stdout.strip()
    assert dims == "1080,1920"
    assert abs(duracao(saida) - 8.0) < 0.5
    ass_original = (tmp_path / "segs" / "seg01.ass").read_text("utf-8")
    assert "PALAVRAS DE TESTE" in ass_original          # fonte em EN, saída em PT: legenda traduzida
    assert "VISÃO DE VETERANO" in (tmp_path / "segs" / "seg00.ass").read_text("utf-8")

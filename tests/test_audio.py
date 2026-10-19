import base64
from types import SimpleNamespace

import pytest

from fabrica.audio import (
    escolher_voz,
    ler_vozes,
    narrar,
    palavras_do_alinhamento,
    transcrever,
)


def test_palavras_do_alinhamento_agrupa_caracteres():
    chars = list("Olá mundo")
    inicios = [0, 1, 2, 3, 4, 5, 6, 7, 8]
    fins = [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert palavras_do_alinhamento(chars, inicios, fins) == [
        {"texto": "Olá", "inicio": 0, "fim": 3},
        {"texto": "mundo", "inicio": 4, "fim": 9},
    ]


def test_transcrever_detecta_idioma_e_filtra_palavras(tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"x")
    palavras = [SimpleNamespace(text="Hi", start=0.0, end=0.3, type="word"),
                SimpleNamespace(text=" ", start=0.3, end=0.4, type="spacing"),
                SimpleNamespace(text="(laughs)", start=0.4, end=1.0, type="audio_event")]
    chamadas = []

    def convert(**kw):
        chamadas.append(kw)
        return SimpleNamespace(words=palavras, language_code="eng")

    cliente = SimpleNamespace(speech_to_text=SimpleNamespace(convert=convert))
    assert transcrever(cliente, audio) == {
        "idioma": "en", "palavras": [{"texto": "Hi", "inicio": 0.0, "fim": 0.3}]}
    assert chamadas[0]["model_id"] == "scribe_v2"
    assert "language_code" not in chamadas[0]
    assert chamadas[0]["request_options"] == {"timeout_in_seconds": 1800}


def test_narrar_usa_v4_grava_mp3_e_devolve_palavras(tmp_path):
    resp = SimpleNamespace(
        audio_base_64=base64.b64encode(b"MP3").decode(),
        alignment=SimpleNamespace(characters=list("Oi"),
                                  character_start_times_seconds=[0.0, 0.1],
                                  character_end_times_seconds=[0.1, 0.2]),
    )
    chamadas = []

    def tts(**kw):
        chamadas.append(kw)
        return resp

    cliente = SimpleNamespace(text_to_speech=SimpleNamespace(convert_with_timestamps=tts))
    destino = tmp_path / "n.mp3"
    assert narrar(cliente, "Oi", destino, "voz", idioma="pt") == [{"texto": "Oi", "inicio": 0.0, "fim": 0.2}]
    assert destino.read_bytes() == b"MP3"
    assert chamadas[0]["model_id"] == "eleven_v4"
    assert chamadas[0]["language_code"] == "pt"


def test_narrar_sem_alinhamento_da_erro_claro(tmp_path):
    resp = SimpleNamespace(audio_base_64=base64.b64encode(b"MP3").decode(), alignment=None)
    cliente = SimpleNamespace(text_to_speech=SimpleNamespace(
        convert_with_timestamps=lambda **kw: resp))
    with pytest.raises(RuntimeError, match="alinhamento"):
        narrar(cliente, "Oi", tmp_path / "n.mp3", "voz", idioma="pt")


def test_ler_vozes_e_escolha_deterministica():
    vozes = ler_vozes("steve:AAA, james:BBB,dean:CCC")
    assert vozes == [("steve", "AAA"), ("james", "BBB"), ("dean", "CCC")]
    assert escolher_voz(vozes, "video:1:en") == escolher_voz(vozes, "video:1:en")
    escolhidas = {escolher_voz(vozes, f"video:{n}:en") for n in range(30)}
    assert len(escolhidas) > 1

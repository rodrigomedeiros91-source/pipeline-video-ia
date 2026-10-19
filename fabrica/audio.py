import base64
import hashlib
import os
import subprocess
from pathlib import Path


CODIGOS_IDIOMA = {"eng": "en", "por": "pt"}


def extrair_audio(video: Path, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.stem + ".tmp" + destino.suffix)
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(video),
         "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", str(tmp)],
        check=True,
    )
    os.replace(tmp, destino)


def transcrever(cliente, audio: Path):
    with open(audio, "rb") as f:
        r = cliente.speech_to_text.convert(
            model_id="scribe_v2", file=f, timestamps_granularity="word",
            request_options={"timeout_in_seconds": 1800},
        )
    return {
        "idioma": CODIGOS_IDIOMA.get(r.language_code, r.language_code),
        "palavras": [{"texto": w.text, "inicio": w.start, "fim": w.end}
                     for w in r.words if w.type == "word"],
    }


def palavras_do_alinhamento(chars, inicios, fins):
    palavras, atual = [], None
    for c, i, f in zip(chars, inicios, fins):
        if c.isspace():
            if atual:
                palavras.append(atual)
            atual = None
        elif atual is None:
            atual = {"texto": c, "inicio": i, "fim": f}
        else:
            atual["texto"] += c
            atual["fim"] = f
    if atual:
        palavras.append(atual)
    return palavras


def narrar(cliente, texto: str, destino: Path, voice_id: str, idioma: str):
    r = cliente.text_to_speech.convert_with_timestamps(
        voice_id=voice_id, text=texto,
        model_id="eleven_v4", output_format="mp3_44100_128", language_code=idioma,
    )
    if r.alignment is None:
        raise RuntimeError("ElevenLabs não devolveu alinhamento para a narração")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(base64.b64decode(r.audio_base_64))
    a = r.alignment
    return palavras_do_alinhamento(a.characters, a.character_start_times_seconds,
                                   a.character_end_times_seconds)


def ler_vozes(texto: str):
    return [tuple(par.strip().split(":", 1)) for par in texto.split(",") if par.strip()]


def escolher_voz(vozes, chave: str):
    """Mesma chave -> mesma voz, para o cache e para não trocar de voz ao rodar de novo."""
    return vozes[int(hashlib.sha1(chave.encode("utf-8")).hexdigest(), 16) % len(vozes)]

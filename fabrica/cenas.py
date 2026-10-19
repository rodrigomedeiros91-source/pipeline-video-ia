"""Cenas ilustradas no estilo do mascote (OpenAI gpt-image-2): quadro 1 e os quadros de pose."""
import base64
import mimetypes
import os
from pathlib import Path

mimetypes.add_type("image/webp", ".webp")  # o Windows não registra .webp; sem isso a OpenAI recebe octet-stream

MODELO = "gpt-image-2"
TAMANHO = "1536x1024"
QUALIDADE = "medium"
CUSTO_IMAGEM = 0.06  # US$ estimado por imagem em qualidade média
REFS = ("neutro", "explicando")  # poses enviadas como referência de estilo

PREFIXO_ESTILO = (
    # stick figure colorido desde 2026-10-18 (who-ruled-italy): o cartum antigo parecia infantil; o P&B, sem vida
    "Illustrate this scene as a colorful minimalist stick-figure animation still for adults, like modern history "
    "explainer channels: every person is a stick figure with a plain round WHITE head, tiny black dot eyes and simple "
    "line expressions, thin black line limbs, wearing simple FULL-COLOR period clothing and headwear with flat fills; "
    "detailed, warmly colored painted backgrounds with soft light and depth, clean black outlines. If the scene mentions "
    "the channel mascot, he appears INSIDE the scene as one of the characters, drawn exactly like the troll in the "
    "reference images (wild white hair, pointed ears, round nose, green suspenders) but dressed for the period when the "
    "scene says so. Wide 3:2 composition, no text, no captions, no watermarks. Scene: ")

POSES_CENA = 4  # q1 base, q2 falando, q3 piscando, q4 gesto

_POSE = ("Redraw this EXACT same image as another frame of the same cartoon animation. Keep "
         "everything identical (composition, characters, colors, background, camera framing) and "
         "change ONLY this: ")
PROMPTS_POSES = {
    2: _POSE + "the characters are talking, mouths open mid-word. No new elements.",
    3: _POSE + "the characters blink, eyes closed in a natural blink. No new elements.",
    4: _POSE + "one character moves an arm or tilts the head into a slightly different pose, "
               "like the next drawing of a gesture. No new elements.",
}


def _editar(cliente, imagens, prompt, destino: Path) -> None:
    arquivos = [open(p, "rb") for p in imagens]
    try:
        resp = cliente.images.edit(model=MODELO, image=arquivos, prompt=prompt,
                                   size=TAMANHO, quality=QUALIDADE)
    finally:
        for a in arquivos:
            a.close()
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp")
    tmp.write_bytes(base64.b64decode(resp.data[0].b64_json))
    os.replace(tmp, destino)


def gerar_quadro1(cliente, cena: str, refs, destino: Path) -> None:
    _editar(cliente, refs, PREFIXO_ESTILO + cena, destino)


def gerar_pose(cliente, q1: Path, destino: Path, n: int) -> None:
    _editar(cliente, [q1], PROMPTS_POSES[n], destino)

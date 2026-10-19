import json
import os
from pathlib import Path


def salvar_json(caminho: Path, dados) -> None:
    """Escrita atômica: grava em .tmp e renomeia, para nunca deixar JSON pela metade."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2), "utf-8")
    os.replace(tmp, caminho)


def etapa(caminho: Path, gerar):
    """Retorna o JSON salvo se existir; senão executa gerar(), salva e retorna."""
    if caminho.exists():
        return json.loads(caminho.read_text("utf-8"))
    dados = gerar()
    salvar_json(caminho, dados)
    return dados


IDIOMAS = {
    "en": {"pps": 2.9, "selo": "VETERAN'S TAKE", "credito": "Source",
           "vozes_env": "ELEVENLABS_VOICES_EN"},
    "pt": {"pps": 2.5, "selo": "VISÃO DE VETERANO", "credito": "Fonte",
           "vozes_env": "ELEVENLABS_VOICES_PT"},
}

"""Busca de imagens de acervo com licença livre na Wikimedia Commons."""
import html
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://commons.wikimedia.org/w/api.php"
# A política da Wikimedia exige User-Agent identificável.
USER_AGENT = "FabricaDeCortes/0.1 (canal de historia; github.com/rodrigomedeiros91-source/pipeline-video-ia)"
MIMES = {"image/jpeg", "image/png", "image/tiff", "image/svg+xml"}
LARGURA_MIN = {"acervo": 1280, "mapa": 800}
MAX_OPCOES = 4


def http_padrao(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def licenca_livre(nome: str) -> bool:
    """Domínio público, CC0, CC BY ou CC BY-SA; qualquer NC/ND reprova."""
    n = (nome or "").strip().lower()
    if re.search(r"\b(nc|nd)\b", n):
        return False
    if n.startswith(("public domain", "pd", "cc0")):
        return True
    return bool(re.match(r"cc[ -]by(-sa)?[ -]\d", n))


def _texto(texto: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", texto or ""))).strip()


def filtrar(resposta: dict, tipo: str) -> list[dict]:
    """Até 4 opções aprovadas (MIME, largura, licença), na ordem de relevância da Commons."""
    paginas = sorted(resposta.get("query", {}).get("pages", {}).values(),
                     key=lambda p: p.get("index", 0))
    opcoes = []
    for p in paginas:
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        licenca = _texto(meta.get("LicenseShortName", {}).get("value", ""))
        mime = info.get("mime", "")
        if mime not in MIMES or not info.get("thumburl"):
            continue
        if mime != "image/svg+xml" and info.get("width", 0) < LARGURA_MIN[tipo]:
            continue
        if not licenca_livre(licenca):
            continue
        opcoes.append({"titulo": p.get("title", "").removeprefix("File:"),
                       "autor": _texto(meta.get("Artist", {}).get("value", "")) or "Unknown author",
                       "licenca": licenca,
                       "url_licenca": meta.get("LicenseUrl", {}).get("value", ""),
                       "pagina": info.get("descriptionurl", ""),
                       "url": info["thumburl"]})
        if len(opcoes) == MAX_OPCOES:
            break
    return opcoes


def _url_busca(busca: str) -> str:
    return API + "?" + urllib.parse.urlencode({
        "action": "query", "generator": "search", "gsrsearch": busca, "gsrnamespace": 6,
        "gsrlimit": 10, "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": 1920, "format": "json"})


def buscar(busca: str, tipo: str, http=http_padrao) -> list[dict]:
    """Busca e filtra; sem nenhuma aprovada, tenta uma vez sem a última palavra."""
    opcoes = filtrar(json.loads(http(_url_busca(busca))), tipo)
    palavras = busca.split()
    if not opcoes and len(palavras) > 1:
        opcoes = filtrar(json.loads(http(_url_busca(" ".join(palavras[:-1])))), tipo)
    return opcoes


def baixar(url: str, destino: Path, http=http_padrao) -> None:
    """Grava em .tmp e renomeia: um download interrompido nunca fica com o nome final."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp")
    tmp.write_bytes(http(url))
    os.replace(tmp, destino)


def extensao(url: str) -> str:
    return Path(urllib.parse.urlparse(url).path).suffix.lower() or ".jpg"

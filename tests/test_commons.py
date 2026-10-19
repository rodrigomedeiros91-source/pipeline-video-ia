import json

import pytest

from fabrica import commons


def pagina(index, titulo="File:A.jpg", mime="image/jpeg", largura=2000,
           licenca="Public domain", artista="<a href='x'>Jane Doe</a>", url_lic="",
           thumb="https://upload.wikimedia.org/a/A.jpg/1920px-A.jpg"):
    """Uma página de arquivo como a API da Commons devolve (generator=search + imageinfo)."""
    return {"index": index, "title": titulo,
            "imageinfo": [{"mime": mime, "width": largura, "thumburl": thumb,
                           "descriptionurl": f"https://commons.wikimedia.org/wiki/{titulo}",
                           "extmetadata": {"LicenseShortName": {"value": licenca},
                                           "Artist": {"value": artista},
                                           "LicenseUrl": {"value": url_lic}}}]}


def resposta(*paginas):
    return {"query": {"pages": {str(-i): p for i, p in enumerate(paginas, 1)}}}


@pytest.mark.parametrize("nome", ["Public domain", "PD-US", "CC0", "CC BY 4.0", "CC BY-SA 3.0",
                                  "cc by-sa 2.5 it", "CC-BY-SA-4.0"])
def test_licenca_livre_aceita(nome):
    assert commons.licenca_livre(nome)


@pytest.mark.parametrize("nome", ["CC BY-NC 4.0", "CC BY-NC-SA 2.0", "CC BY-ND 4.0", "Fair use",
                                  "", "All rights reserved"])
def test_licenca_livre_recusa(nome):
    assert not commons.licenca_livre(nome)


def test_filtrar_ordena_por_index():
    r = resposta(pagina(2, "File:B.jpg"), pagina(1, "File:A.jpg"))
    assert [o["titulo"] for o in commons.filtrar(r, "acervo")] == ["A.jpg", "B.jpg"]


def test_filtrar_campos_de_credito():
    o = commons.filtrar(resposta(pagina(1, url_lic="https://cc/by")), "acervo")[0]
    assert o == {"titulo": "A.jpg", "autor": "Jane Doe", "licenca": "Public domain",
                 "url_licenca": "https://cc/by",
                 "pagina": "https://commons.wikimedia.org/wiki/File:A.jpg",
                 "url": "https://upload.wikimedia.org/a/A.jpg/1920px-A.jpg"}


def test_filtrar_autor_vazio():
    assert commons.filtrar(resposta(pagina(1, artista="")), "acervo")[0]["autor"] == "Unknown author"


def test_filtrar_mime():
    r = resposta(pagina(1, "File:A.pdf", mime="application/pdf"),
                 pagina(2, "File:B.tif", mime="image/tiff"))
    assert [o["titulo"] for o in commons.filtrar(r, "acervo")] == ["B.tif"]


def test_filtrar_largura_por_tipo():
    r = resposta(pagina(1, largura=1000))
    assert commons.filtrar(r, "acervo") == []
    assert len(commons.filtrar(r, "mapa")) == 1


def test_filtrar_svg_isento_de_largura():
    r = resposta(pagina(1, mime="image/svg+xml", largura=300))
    assert len(commons.filtrar(r, "acervo")) == 1


def test_filtrar_licenca():
    assert commons.filtrar(resposta(pagina(1, licenca="CC BY-NC 4.0")), "acervo") == []


def test_filtrar_limite_de_4():
    r = resposta(*[pagina(i, f"File:{i}.jpg") for i in range(1, 8)])
    assert [o["titulo"] for o in commons.filtrar(r, "acervo")] == ["1.jpg", "2.jpg", "3.jpg", "4.jpg"]


def test_filtrar_resposta_vazia():
    assert commons.filtrar({}, "acervo") == []
    assert commons.filtrar({"batchcomplete": ""}, "mapa") == []


def test_buscar_parametros():
    urls = []

    def http(url):
        urls.append(url)
        return b"{}"

    commons.buscar("Galileo", "mapa", http)
    assert urls[0].startswith(commons.API + "?")
    for p in ("generator=search", "gsrsearch=Galileo", "gsrnamespace=6", "gsrlimit=10",
              "prop=imageinfo", "iiurlwidth=1920", "format=json"):
        assert p in urls[0]


def test_buscar_repete_sem_ultima_palavra():
    urls = []

    def http(url):
        urls.append(url)
        return json.dumps(resposta(pagina(1)) if len(urls) == 2 else {}).encode()

    assert len(commons.buscar("Paul Revere ride 1775", "acervo", http)) == 1
    assert "gsrsearch=Paul+Revere+ride&" in urls[1]


def test_buscar_uma_palavra_nao_repete():
    urls = []

    def http(url):
        urls.append(url)
        return b"{}"

    assert commons.buscar("Revere", "acervo", http) == []
    assert len(urls) == 1


def test_baixar_grava_atomico(tmp_path):
    destino = tmp_path / "imagens" / "1.1-A.jpg"
    commons.baixar("https://x/a.jpg", destino, lambda url: b"abc")
    assert destino.read_bytes() == b"abc"
    assert not list(tmp_path.rglob("*.tmp"))


def test_baixar_erro_nao_deixa_arquivo(tmp_path):
    def http(url):
        raise OSError("rede")

    with pytest.raises(OSError):
        commons.baixar("https://x/a.jpg", tmp_path / "a.jpg", http)
    assert not (tmp_path / "a.jpg").exists()


@pytest.mark.parametrize("url,ext", [
    ("https://u/x/1920px-A.jpg", ".jpg"),
    ("https://u/x/1920px-M.svg.png", ".png"),
    ("https://u/x/1920px-T.tif.jpg", ".jpg"),
    ("https://u/x/A.JPEG?x=1", ".jpeg"),
    ("https://u/x/semext", ".jpg"),
])
def test_extensao(url, ext):
    assert commons.extensao(url) == ext


def test_filtrar_decodifica_entidades_do_autor():
    o = commons.filtrar(resposta(pagina(1, artista="<b>Smith &amp; Sons</b>&#160;Ltd")), "acervo")[0]
    assert o["autor"] == "Smith & Sons Ltd"

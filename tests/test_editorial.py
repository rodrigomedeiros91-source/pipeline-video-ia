from fabrica.editorial import (
    compactar_transcricao,
    janela_contexto,
    status,
    validar_idiomas,
    validar_receita,
)


def p(texto, inicio):
    return {"texto": texto, "inicio": inicio, "fim": inicio + 0.4}


def narr(n, inicio=100.0):
    return {"tipo": "narracao", "en": " ".join(["word"] * n), "pt": " ".join(["palavra"] * n),
            "inicio": inicio, "fim": 0, "legenda_en": "", "legenda_pt": ""}


def orig(inicio, fim):
    return {"tipo": "original", "en": "", "pt": "", "inicio": inicio, "fim": fim,
            "legenda_en": "x", "legenda_pt": "x"}


MOMENTO = {"inicio": 100.0, "fim": 160.0, "tema": "guide", "motivo": "x", "score_viral": 90}


def receita(blocos, score=90, fiel=True):
    return {"tema": "guide", "blocos": blocos, "en": {}, "pt": {}, "score": score,
            "fiel_ao_contexto": fiel, "alertas": []}


def test_compactar_quebra_em_fim_de_frase():
    palavras = [p("Olá", 0.0), p("mundo.", 0.5), p("Tudo", 1.0), p("bem?", 1.5)]
    assert compactar_transcricao(palavras) == "[0.0] Olá mundo.\n[1.0] Tudo bem?"


def test_compactar_quebra_por_tamanho():
    palavras = [p("a", float(i)) for i in range(5)]
    assert compactar_transcricao(palavras, max_palavras=2) == "[0.0] a a\n[2.0] a a\n[4.0] a"


def test_janela_contexto_recorta_antes_e_depois():
    palavras = [p("x.", float(t)) for t in (0, 50, 100, 150, 200, 260)]
    texto = janela_contexto(palavras, 100, 150, antes=60, depois=60)
    assert texto == "[50.0] x.\n[100.0] x.\n[150.0] x.\n[200.0] x."


def test_receita_valida_nos_dois_idiomas():
    # EN: 120/2.9 = 41.4 s + 24 s = 65.4 s (63%); PT: 120/2.5 = 48 s + 24 s = 72 s (67%)
    r = receita([narr(60), orig(100, 112), narr(60), orig(120, 132)])
    assert validar_idiomas(r, MOMENTO) == {"en": [], "pt": []}


def test_short_100_por_cento_narrado_e_valido():
    # EN 69 s, PT 80 s, sem trecho original
    assert validar_idiomas(receita([narr(200)]), MOMENTO) == {"en": [], "pt": []}


def test_idiomas_validados_separadamente():
    # EN 58.6 s (curto demais), PT 68 s
    erros = validar_idiomas(receita([narr(170)]), MOMENTO)
    assert any("61 e 90" in e for e in erros["en"])
    assert erros["pt"] == []


def test_trecho_original_longo_demais():
    r = receita([narr(200), orig(100, 120)])
    assert any("15 s" in e for e in validar_receita(r, MOMENTO, "pt"))


def test_trecho_fora_do_momento():
    r = receita([narr(200), orig(300, 310)])
    assert any("fora do momento" in e for e in validar_receita(r, MOMENTO, "pt"))


def test_gameplay_da_narracao_fora_da_janela():
    r = receita([narr(200, inicio=500.0)])
    assert any("fora da janela" in e for e in validar_receita(r, MOMENTO, "pt"))


def test_narracao_insuficiente():
    # EN: 20/2.9 = 6.9 s de narração + 60 s de originais -> 10%
    r = receita([narr(20), orig(100, 115), orig(115, 130), orig(130, 145), orig(145, 160)])
    assert any("40%" in e for e in validar_receita(r, MOMENTO, "en"))


def test_duracao_longa_demais():
    r = receita([narr(300)])
    assert any("61 e 90" in e for e in validar_receita(r, MOMENTO, "en"))


def test_narracao_vazia_num_idioma():
    bloco = narr(200)
    bloco["pt"] = "   "
    erros = validar_idiomas(receita([narr(100), bloco]), MOMENTO)
    assert any("vazio" in e for e in erros["pt"])
    assert not any("vazio" in e for e in erros["en"])


def test_status():
    assert status(receita([], score=90)) == "pronto"
    assert status(receita([], score=70)) == "revisar"
    assert status(receita([], score=50)) == "descartado"
    assert status(receita([], score=95, fiel=False)) == "descartado"

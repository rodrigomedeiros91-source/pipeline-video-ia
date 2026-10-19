from fabrica import saidas


def p(texto, ini, fim):
    return {"texto": texto, "inicio": ini, "fim": fim}


def test_tempo_srt():
    assert saidas.tempo_srt(0) == "00:00:00,000"
    assert saidas.tempo_srt(3723.4567) == "01:02:03,457"


def test_tempo_capitulo():
    assert saidas.tempo_capitulo(0) == "0:00"
    assert saidas.tempo_capitulo(75.9) == "1:15"
    assert saidas.tempo_capitulo(3725) == "1:02:05"


def test_legendas_quebra_no_fim_de_frase():
    srt = saidas.legendas([p("Hello", 0, 0.5), p("there.", 0.5, 1.0), p("New", 1.2, 1.5),
                           p("cue", 1.5, 2.0)])
    assert srt == ("1\n00:00:00,000 --> 00:00:01,000\nHello there.\n\n"
                   "2\n00:00:01,200 --> 00:00:02,000\nNew cue\n")


def test_legendas_aspas_depois_do_ponto():
    srt = saidas.legendas([p('"Done."', 0, 0.5), p("Next", 0.6, 1.0)])
    assert srt.count(" --> ") == 2


def test_legendas_limite_de_caracteres():
    palavras = [p("word", i * 0.3, i * 0.3 + 0.25) for i in range(30)]
    for bloco in saidas.legendas(palavras).strip().split("\n\n"):
        linhas = bloco.split("\n")[2:]
        assert 1 <= len(linhas) <= 2
        assert all(len(linha) <= 42 for linha in linhas)


def test_legendas_limite_de_tempo():
    palavras = [p("a", float(i), i + 0.5) for i in range(10)]
    primeiro = saidas.legendas(palavras).split("\n\n")[0]
    assert primeiro.split("\n")[1] == "00:00:00,000 --> 00:00:05,500"


def test_legendas_aspas_curvas_e_parenteses():
    srt = saidas.legendas([p("“Done.”", 0, 0.5), p("(see", 0.6, 0.8), p("above.)", 0.8, 1.0),
                           p("Next", 1.1, 1.5)])
    assert srt.count(" --> ") == 3


def test_descricao():
    roteiro = {"titulo": "T", "descricao_youtube": "Desc.\n", "tags": ["history", "myths"],
               "capitulos": [{"fontes": [{"url": "https://a"}, {"url": "https://b"}]},
                             {"fontes": [{"url": "https://a"}]}]}
    caps = [{"id": "intro", "titulo": "Intro", "inicio": 0.0},
            {"id": "1", "titulo": "Cake", "inicio": 65.4},
            {"id": "2", "titulo": "Voltaire", "inicio": 130.0},
            {"id": "outro", "titulo": "Outro", "inicio": 3700.0}]
    assert saidas.descricao(roteiro, caps, "Images from Wikimedia Commons:\n- x\n") == (
        "TITLE: T\n\nDesc.\n\nChapters:\n0:00 Intro\n1:05 #1 Cake\n2:10 #2 Voltaire\n"
        "1:01:40 Outro\n\nSources:\n- https://a\n- https://b\n\n"
        "Images from Wikimedia Commons:\n- Other images: public domain / CC0, via Wikimedia Commons.\n\n"
        "TAGS: history, myths\n")


def test_creditos_obrigatorios():
    c = ('Images from Wikimedia Commons:\n- "A" by X, Public domain — p1\n- "B" by Y, CC BY-SA 4.0 (u) — p2\n'
         '- "C" by Z, CC0 (u) — p3\n\nIllustrations and mascot: original artwork for this channel.\n')
    assert saidas.creditos_obrigatorios(c) == (
        'Images from Wikimedia Commons:\n- "B" by Y, CC BY-SA 4.0 (u) — p2\n'
        "- Other images: public domain / CC0, via Wikimedia Commons.\n\n"
        "Illustrations and mascot: original artwork for this channel.")

from fabrica import recortes


def roteiro():
    t = lambda n: {"narracao": n}
    return {"intro": [t("Hello there world.")], "outro": [t("Bye now.")],
            "capitulos": [{"titulo": "One", "short": {}, "trechos": [t("In 509 BC Rome"), t("threw out its king.")]}]}


def test_validar_exige_as_frases_da_narracao():
    rec = {"blocos": {"intro": [{"frase": "Hello there", "cena": "a"}, {"frase": "world.", "cena": "b"}],
                      "1": [{"frase": "In 509 BC Rome threw out its king.", "cena": "c"}],
                      "outro": [{"frase": "Bye now.", "cena": "d"}]}}
    assert recortes.validar(roteiro(), rec) == []
    rec["blocos"]["1"][0]["frase"] = "In 509 BC Rome threw out the king."
    rec["blocos"]["outro"][0]["cena"] = " "
    erros = recortes.validar(roteiro(), rec)
    assert "bloco 1: as frases não reproduzem a narração palavra por palavra" in erros
    assert "bloco outro cena 1: sem descrição" in erros


def test_ass_frase_no_meio_e_titulo():
    txt = recortes.ass([("the Romans {arrive}", 0.0, 2.5), ("", 2.5, 3.0)], recortes.HORIZ, ("WHO RULED\nITALY?", 0.0, 2.5))
    assert r"Frase,,0,0,0,,{\pos(960,800)}the Romans (arrive)" in txt and "PlayResX: 1920" in txt
    assert r"{\pos(540,1180)}" in recortes.ass([("x", 0.0, 1.0)], recortes.VERT)
    assert txt.count("Dialogue:") == 2 and r"WHO RULED\NITALY?" in txt


def test_eventos_sem_deriva_e_movimento_alternado():
    ev = recortes.eventos([("a", 0.0, 1.01, "x"), ("b", 1.01, 2.0, "y"), ("c", 2.0, 3.0, "z")])
    assert sum(e["quadros"] for e in ev) == 90
    assert [e["pan"] for e in ev] == [0, 1, -1]


def test_espacar_so_pausa_no_fim_da_sentenca():
    segs, novos, dur = recortes.espacar("n.wav", [(0.0, 2.0), (2.0, 5.0), (5.0, 6.0)],
                                        ["Rome grew,", "then it fell.", "Why?"], [0.1, 0.4, float("inf")], 0.5)
    assert segs == [("n.wav", 0.0, 5.0), 0.5, ("n.wav", 5.0, 6.0), 0.5]  # sem corte no meio da oração
    assert novos == [(0.0, 2.0), (2.0, 5.5), (5.5, 7.0)] and dur == 7.0


def test_srt_uma_frase_por_bloco():
    txt = recortes.srt([("the Romans arrive", 0.0, 2.5), ("then Caesar", 2.5, 4.0)])
    assert txt.startswith("1\n00:00:00,000 --> 00:00:02,500\nthe Romans arrive\n")
    assert "2\n00:00:02,500 --> 00:00:04,000\nthen Caesar" in txt


def test_espacar_nao_corta_sentenca_emendada():
    segs, _, _ = recortes.espacar("n.wav", [(0.0, 2.0), (2.0, 3.0)], ["It fell.", "Why?"], [0.05, float("inf")], 0.5)
    assert segs == [("n.wav", 0.0, 3.0), 0.5]


def test_folgas_entre_frases():
    pal = [{"inicio": 0.0, "fim": 0.4}, {"inicio": 0.5, "fim": 0.9}, {"inicio": 1.2, "fim": 1.5}]
    assert [round(g, 2) for g in recortes.folgas(pal, ["a b", "c"])[:1]] == [0.3]

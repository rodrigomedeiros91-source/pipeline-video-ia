import datetime as dt

from fabrica import shorts
from fabrica.render import tempo_ass
from tests.test_roteiro import roteiro


def p(texto, ini, fim):
    return {"texto": texto, "inicio": ini, "fim": fim}


def test_eventos_short_com_cartao_final_sem_deriva():
    eventos, total = shorts.eventos_short([("1.1", 0.0, 1.25), ("1.2", 1.25, 4.0)], 4.0)
    assert total == 7.0
    assert [e["id"] for e in eventos] == ["1.1", "1.2", "fim"]
    assert [e["quadros"] for e in eventos] == [38, 82, 90]
    assert sum(e["quadros"] for e in eventos) == round(total * 30)


def test_blocos_legenda_tres_palavras_e_fim_de_frase():
    pal = [p("Hello", 0.0, 0.3), p("there,", 0.3, 0.6), p("my", 0.7, 0.8), p("friend.", 0.8, 1.2),
           p("Next", 2.0, 2.3)]
    assert shorts.blocos_legenda(pal) == [
        {"texto": "HELLO THERE, MY", "inicio": 0.0, "fim": 0.8},
        {"texto": "FRIEND.", "inicio": 0.8, "fim": 1.2},
        {"texto": "NEXT", "inicio": 2.0, "fim": 2.3},
    ]


def test_blocos_legenda_emendam_pausas_curtas():
    blocos = shorts.blocos_legenda([p("a", 0.0, 0.2), p("b", 0.2, 0.4), p("c", 0.4, 0.6),
                                    p("d", 0.9, 1.0)])
    assert blocos[0]["fim"] == 0.9


def test_ass():
    texto = shorts.ass([{"texto": "HI {THERE}", "inicio": 1.5, "fim": 2.25}])
    assert "PlayResX: 1080" in texto and "PlayResY: 1920" in texto
    assert "Style: Legenda,Impact,88," in texto and ",2,60,60,330,1" in texto
    assert texto.rstrip().endswith("Dialogue: 0,0:00:01.50,0:00:02.25,Legenda,,0,0,0,,HI (THERE)")


def test_textos_por_rede():
    short = {"titulo": "Marie Antoinette Never Said It? #Shorts", "hashtags": ["#history", "#france"]}
    t = shorts.textos(short)
    assert shorts.gancho(short) == "Marie Antoinette Never Said It?"
    assert t["descricao_youtube"] == ("Marie Antoinette Never Said It?\n\nFull story: {link_longo}\n\n"
                                      "#history #france")
    assert t["texto_tiktok"] == ("Marie Antoinette Never Said It? #history #france #historytok #didyouknow"
                                 "\nFull video on YouTube: The Myth Troll")
    assert t["texto_instagram"] == ("Marie Antoinette Never Said It?\n\nFull video: link in bio\n\n"
                                    "#history #france #historyfacts #didyouknow")


def test_datas():
    assert shorts.proximo_sabado(dt.date(2026, 10, 3)) == dt.date(2026, 10, 10)   # sábado → o seguinte
    assert shorts.proximo_sabado(dt.date(2026, 10, 5)) == dt.date(2026, 10, 10)
    assert shorts.datas(dt.date(2026, 10, 10), 3) == [dt.date(2026, 10, 10), dt.date(2026, 10, 10),
                                                     dt.date(2026, 10, 11), dt.date(2026, 10, 12)]


def test_pacote_novo():
    r = roteiro()
    pac = shorts.pacote(r, "roman-myths", dt.date(2026, 10, 10))
    assert pac["fuso"] == "America/Sao_Paulo"
    assert pac["longo"]["data"] == "2026-10-10"
    assert pac["longo"]["hora"] == "16:00" and pac["longo"]["status"] == "pendente"
    assert pac["longo"]["thumbnail"] == "historia/canal/thumbs/roman-myths.jpg"
    assert [s["n"] for s in pac["shorts"]] == [1, 2, 3, 4, 5, 6]
    s1 = pac["shorts"][0]
    assert (s1["data"], s1["hora"], s1["arquivo"]) == ("2026-10-10", "20:00",
                                                      "historia/shorts/roman-myths/short-1.mp4")
    assert (pac["shorts"][1]["data"], pac["shorts"][1]["hora"]) == ("2026-10-11", "13:00")
    assert "{link_longo}" in s1["descricao_youtube"]


def test_pacote_preserva_o_que_ja_foi_agendado():
    r = roteiro()
    anterior = shorts.pacote(r, "roman-myths", dt.date(2026, 10, 10))
    anterior["longo"] |= {"status": "agendado", "url": "https://youtu.be/LONGO", "playlist": "Fake Quotes"}
    anterior["shorts"][0] |= {"status": "agendado", "url": "https://youtu.be/S1"}
    novo = shorts.pacote(r, "roman-myths", dt.date(2026, 10, 17), anterior)
    assert novo["longo"]["status"] == "agendado" and novo["longo"]["data"] == "2026-10-10"
    assert novo["longo"]["playlist"] == "Fake Quotes"
    assert novo["shorts"][0]["url"] == "https://youtu.be/S1" and novo["shorts"][0]["data"] == "2026-10-10"
    assert novo["shorts"][1]["data"] == "2026-10-18"          # pendente segue o novo início
    assert "https://youtu.be/LONGO" in novo["shorts"][1]["descricao_youtube"]


def test_pacote_sem_thumbnail():
    pac = shorts.pacote(roteiro(), "roman-myths", dt.date(2026, 10, 10), thumbnail_existe=False)
    assert pac["longo"]["thumbnail"] == ""
    assert "thumbnail ausente" in shorts.calendario_md(pac)


def test_calendario_md():
    pac = shorts.pacote(roteiro(), "roman-myths", dt.date(2026, 10, 10))
    md = shorts.calendario_md(pac)
    assert "| 2026-10-10 | 16:00 | Vídeo longo |" in md
    assert "| 2026-10-10 | 20:00 | Short 1:" in md
    assert pac["shorts"][0]["texto_tiktok"] in md and pac["shorts"][0]["texto_instagram"] in md


def test_blocos_legenda_aspas_curvas():
    blocos = shorts.blocos_legenda([p("He", 0.0, 0.2), p("said", 0.2, 0.4), p("”go.”", 0.4, 0.6),
                                    p("Ok", 1.5, 1.8)])
    assert [b["texto"] for b in blocos] == ["HE SAID ”GO.”", "OK"]


def test_tempo_ass_arredonda_sem_60_segundos():
    assert tempo_ass(59.996) == "0:01:00.00"
    assert tempo_ass(1.5) == "0:00:01.50"
    assert tempo_ass(3723.456) == "1:02:03.46"


def test_planos_dividem_visual_parado():
    eventos, total = shorts.eventos_short([("1.1", 0.0, 12.0), ("1.2", 12.0, 15.0)], 15.0, divisiveis={"1.1"})
    assert total == 18.0
    assert [e["id"] for e in eventos] == ["1.1-1", "1.1-2", "1.1-3", "1.2", "fim"]
    assert [e["fonte"] for e in eventos] == ["1.1", "1.1", "1.1", "1.2", "fim"]
    assert [e["pan"] for e in eventos[:4]] == [0, 1, -1, 0]
    assert sum(e["quadros"] for e in eventos) == round(total * 30)


def test_cartao_final_dura_pergunta_mais_fim():
    eventos, total = shorts.eventos_short([("1.1", 0.0, 4.0)], 4.0, fim=2.0 + shorts.FIM)
    assert eventos[-1] | {} == eventos[-1] and eventos[-1]["ini"] == 4.0 and total == 9.0


def test_montar_short_escolha_abertura_pergunta():
    todos = [("1.1", 0.0, 2.0), ("1.2", 2.0, 5.0), ("1.3", 5.0, 7.0)]
    palavras = [p("one", 0.1, 0.5), p("two", 2.5, 3.0), p("three", 5.2, 5.6)]
    m = shorts.montar_short(todos, palavras, [1, 3], abertura=(1.0, [p("Fake.", 0.0, 0.5)]),
                            pergunta=(1.5, [p("Why?", 0.0, 0.4)]))
    assert m["audio"] == ["abertura", (0.0, 2.0), (5.0, 7.0), "pergunta"]
    assert m["visuais"] == [("1.1", 0.0, 3.0), ("1.3", 3.0, 5.0)]
    assert m["fim_trechos"] == 5.0 and m["fim"] == 1.5 + shorts.FIM
    assert [(w["texto"], w["inicio"]) for w in m["palavras"]] == [("Fake.", 0.0), ("one", 1.1), ("three", 3.2),
                                                                 ("Why?", 5.0)]


def test_montar_short_sem_escolha_usa_tudo():
    todos = [("1.1", 0.0, 2.0), ("1.2", 2.0, 5.0)]
    m = shorts.montar_short(todos, [p("a", 0.0, 0.2)], None)
    assert m["audio"] == [(0.0, 2.0), (2.0, 5.0)] and m["visuais"] == todos and m["fim"] == shorts.FIM


def test_montar_short_trava_60_segundos():
    todos = [(f"1.{k}", k * 12.0, (k + 1) * 12.0) for k in range(8)]
    try:
        shorts.montar_short(todos, [], None)
    except ValueError as e:
        assert "60" in str(e)
    else:
        raise AssertionError("deveria recusar Short com mais de 60 s")


def test_textos_com_pergunta_na_legenda():
    t = shorts.textos({"titulo": "Myth #Shorts", "hashtags": ["#a"], "pergunta": "Which one next?"})
    assert t["texto_tiktok"] == ("Myth\nWhich one next? 👇\n#a #history #historytok #didyouknow\n"
                                 "Full video on YouTube: The Myth Troll")
    assert t["texto_instagram"] == ("Myth\n\nWhich one next? 👇\nFull video: link in bio\n\n"
                                    "#a #history #historyfacts #didyouknow")
    assert "Which" not in t["descricao_youtube"]

from fabrica.render import (gerar_ass, inicio_gameplay, legenda_distribuida, palavras_do_trecho,
                            slug, tempo_ass)


def test_tempo_ass():
    assert tempo_ass(0) == "0:00:00.00"
    assert tempo_ass(3725.5) == "1:02:05.50"


def test_slug_remove_acentos_e_simbolos():
    assert slug("O erro de olhar só para faturamento!") == "o-erro-de-olhar-so-para-faturamento"


def test_gerar_ass_agrupa_palavras_e_tem_credito():
    palavras = [{"texto": t, "inicio": i, "fim": i + 0.4}
                for i, t in enumerate(["um", "dois", "três", "quatro"])]
    ass = gerar_ass(palavras, 5.0, "Fonte: Podcast X", por_linha=3)
    assert "PlayResX: 1080" in ass
    assert "Dialogue: 0,0:00:00.00,0:00:02.40,Legenda,,0,0,0,,UM DOIS TRÊS" in ass
    assert "Dialogue: 0,0:00:03.00,0:00:03.40,Legenda,,0,0,0,,QUATRO" in ass
    assert "Dialogue: 0,0:00:00.00,0:00:05.00,Credito,,0,0,0,,Fonte: Podcast X" in ass
    assert "Selo" not in ass.split("[Events]")[1]


def test_gerar_ass_com_selo():
    ass = gerar_ass([], 2.0, "Fonte: X", selo="ANÁLISE")
    assert "Dialogue: 0,0:00:00.00,0:00:02.00,Selo,,0,0,0,,ANÁLISE" in ass


def test_legenda_distribuida_divide_o_tempo_por_igual():
    assert legenda_distribuida("um dois três quatro", 2.0) == [
        {"texto": "um", "inicio": 0.0, "fim": 0.5},
        {"texto": "dois", "inicio": 0.5, "fim": 1.0},
        {"texto": "três", "inicio": 1.0, "fim": 1.5},
        {"texto": "quatro", "inicio": 1.5, "fim": 2.0},
    ]
    assert legenda_distribuida("", 2.0) == []


def test_inicio_gameplay_recua_para_caber_na_fonte():
    assert inicio_gameplay(19.5, 2.0, 20.0) == 18.0
    assert inicio_gameplay(5.0, 2.0, 20.0) == 5.0
    assert inicio_gameplay(5.0, 30.0, 20.0) == 0.0


def test_palavras_do_trecho_filtra_e_desloca():
    palavras = [{"texto": "a", "inicio": 1.0, "fim": 1.4},
                {"texto": "b", "inicio": 2.5, "fim": 3.0},
                {"texto": "c", "inicio": 5.8, "fim": 6.2}]
    assert palavras_do_trecho(palavras, 2.0, 6.0) == [{"texto": "b", "inicio": 0.5, "fim": 1.0}]


def test_tela_com_largura_da_imagem_inteira_nao_corta_as_laterais():
    from fabrica.render import TELA, tela
    assert "scale=1700:-2" in TELA
    assert "[frente]scale=1080:-2,crop=1080:ih" in tela(1080)


def test_gerar_ass_com_gancho_no_topo_so_no_comeco():
    ass = gerar_ass([], 20.0, "", gancho="He offered MORE")
    assert "Dialogue: 0,0:00:00.00,0:00:03.00,Gancho,,0,0,0,,He offered MORE" in ass
    assert "Gancho" not in gerar_ass([], 20.0, "").split("[Events]")[1]
    assert "0:00:02.00,Gancho" in gerar_ass([], 2.0, "", gancho="curto")

import json

from fabrica.roteiro import main, validar_roteiro

CAMPO = {"acervo": "busca", "mapa": "busca", "texto": "texto_tela",
         "linha_tempo": "texto_tela", "cena": "cena"}


def trecho(n=30, tipo="acervo", mascote="neutro"):
    visual = {"tipo": tipo, "busca": "", "cena": "", "texto_tela": "",
              "mascote": "" if tipo == "cena" else mascote}
    visual[CAMPO[tipo]] = "x"
    return {"narracao": " ".join(["word"] * n), "visual": visual}


def capitulo():
    # 8 trechos de 30 palavras = 240 palavras, 1 cena
    return {"titulo": "Gladiators", "short": {"titulo": "Myth #Shorts",
                                               "hashtags": ["#history", "#rome"]},
            "trechos": [trecho(30, "cena")] + [trecho(30) for _ in range(7)],
            "fontes": [{"afirmacao": "a", "url": "https://example.org"}]}


def roteiro():
    return {"slug": "roman-myths", "formato": 2, "titulo": "T", "descricao_youtube": "d",
            "tags": ["history"],
            "intro": [trecho(20), trecho(20)],                 # 40 palavras
            "capitulos": [capitulo() for _ in range(6)],
            "outro": [trecho(25), trecho(25)],                 # 50 palavras
            "alertas": []}


def erros_com(texto, r):
    return [e for e in validar_roteiro(r) if texto in e]


def test_roteiro_valido():
    assert validar_roteiro(roteiro()) == []


def test_todos_os_tipos_validos():
    r = roteiro()
    r["capitulos"][0]["trechos"][1:5] = [trecho(30, t) for t in ("mapa", "texto", "linha_tempo", "acervo")]
    assert validar_roteiro(r) == []


def test_falta_campo_de_topo():
    r = roteiro()
    del r["alertas"]
    assert validar_roteiro(r) == ["faltam campos: alertas"]


def test_numero_de_capitulos():
    r = roteiro()
    r["capitulos"] = r["capitulos"][:5]
    assert erros_com("5 capítulos", r)


def test_palavras_por_capitulo():
    r = roteiro()
    del r["capitulos"][0]["trechos"][-2:]                # 180 palavras
    assert erros_com("capítulo 1: 180 palavras", r)


def test_intro_e_outro():
    r = roteiro()
    r["intro"] = [trecho(30), trecho(30), trecho(30)]  # 90
    r["outro"] = [trecho(40), trecho(40), trecho(20)]  # 100
    assert erros_com("intro: 90 palavras", r)
    assert erros_com("outro: 100 palavras", r)


def test_trecho_curto_ou_longo():
    r = roteiro()
    r["capitulos"][0]["trechos"][1] = trecho(8)
    r["capitulos"][0]["trechos"][2] = trecho(52)
    assert erros_com("capítulo 1 trecho 2: narração com 8 palavras", r)
    assert erros_com("capítulo 1 trecho 3: narração com 52 palavras", r)


def test_tipo_invalido():
    r = roteiro()
    r["capitulos"][0]["trechos"][1]["visual"]["tipo"] = "video"
    assert erros_com("tipo de visual inválido 'video'", r)


def test_campo_obrigatorio_do_tipo_vazio():
    r = roteiro()
    r["capitulos"][0]["trechos"][1]["visual"]["busca"] = " "
    assert erros_com("visual 'acervo' exige 'busca'", r)


def test_visual_sem_campo():
    r = roteiro()
    del r["capitulos"][0]["trechos"][1]["visual"]["mascote"]
    assert erros_com("visual sem mascote", r)


def test_cena_nao_leva_mascote():
    r = roteiro()
    r["capitulos"][0]["trechos"][0]["visual"]["mascote"] = "rindo"
    assert erros_com("cena não leva mascote", r)


def test_pose_desconhecida():
    r = roteiro()
    r["capitulos"][0]["trechos"][1]["visual"]["mascote"] = "dancando"
    assert erros_com("pose desconhecida 'dancando'", r)


def test_pose_extra_aceita():
    r = roteiro()
    r["capitulos"][0]["trechos"][1]["visual"]["mascote"] = "placa_interrogacao"
    assert validar_roteiro(r) == []


def test_cenas_por_capitulo():
    r = roteiro()
    r["capitulos"][0]["trechos"][0] = trecho(30)                          # 0 cenas
    r["capitulos"][1]["trechos"][:4] = [trecho(30, "cena") for _ in range(4)]  # 4 cenas
    assert erros_com("capítulo 1: 0 cenas", r)
    assert erros_com("capítulo 2: 4 cenas", r)


def test_fontes():
    r = roteiro()
    r["capitulos"][0]["fontes"] = []
    r["capitulos"][1]["fontes"] = [{"afirmacao": "a", "url": "example.org"}]
    assert erros_com("capítulo 1: precisa de pelo menos 1 fonte", r)
    assert erros_com("capítulo 2: fonte sem url http", r)


def test_titulo_do_short():
    r = roteiro()
    r["capitulos"][0]["short"]["titulo"] = "Myth"
    r["capitulos"][1]["short"]["titulo"] = "x" * 95 + " #Shorts"
    assert erros_com("capítulo 1: título do Short", r)
    assert erros_com("capítulo 2: título do Short", r)


def test_hashtags_do_short():
    r = roteiro()
    r["capitulos"][0]["short"]["hashtags"] = ["#history"]
    r["capitulos"][1]["short"]["hashtags"] = ["#history", "rome"]
    assert erros_com("capítulo 1: hashtags", r)
    assert erros_com("capítulo 2: hashtags", r)


def test_capitulo_sem_titulo():
    r = roteiro()
    r["capitulos"][0]["titulo"] = ""
    assert erros_com("capítulo 1: sem título", r)


def test_main_ok_e_erro(tmp_path, capsys):
    bom = tmp_path / "roman-myths.json"
    bom.write_text(json.dumps(roteiro()), "utf-8")
    assert main([str(bom)]) == 0
    assert capsys.readouterr().out.strip() == "OK"

    r = roteiro()
    r["capitulos"] = r["capitulos"][:5]
    ruim = tmp_path / "ruim.json"
    ruim.write_text(json.dumps(r), "utf-8")
    assert main([str(ruim)]) == 1
    assert "5 capítulos" in capsys.readouterr().out


def test_main_uso_errado(capsys):
    assert main([]) == 2
    assert "uso:" in capsys.readouterr().out


def test_formato_invalido():
    r = roteiro()
    r["capitulos"][0]["trechos"][1]["narracao"] = None
    r["capitulos"][1] = "oops"
    erros = validar_roteiro(r)
    assert any("capítulo 1 trecho 2: formato inválido" in e for e in erros)
    assert any("capítulo 2: formato inválido" in e for e in erros)


def test_main_arquivo_invalido(tmp_path, capsys):
    # Missing file
    assert main([str(tmp_path / "nao_existe.json")]) == 2
    assert "erro ao ler" in capsys.readouterr().out

    # Invalid JSON
    ruim = tmp_path / "invalido.json"
    ruim.write_text("{invalid", "utf-8")
    assert main([str(ruim)]) == 2
    assert "erro ao ler" in capsys.readouterr().out


def test_contrato_de_topo():
    for campo, valor, texto in [
        ("slug", "Roman Myths", "slug inválido 'Roman Myths' (use kebab-case)"),
        ("slug", "roman--myths", "slug inválido"),
        ("titulo", "", "titulo deve ter 1–100 caracteres"),
        ("titulo", "x" * 101, "titulo deve ter 1–100 caracteres"),
        ("descricao_youtube", "  ", "descricao_youtube vazia"),
        ("tags", [], "tags deve ser lista não vazia de textos"),
        ("tags", ["ok", 5], "tags deve ser lista não vazia de textos"),
        ("alertas", "x", "alertas deve ser lista"),
    ]:
        r = roteiro()
        r[campo] = valor
        assert erros_com(texto, r), (campo, valor)


def test_slug_diferente_do_arquivo(tmp_path, capsys):
    f = tmp_path / "outro-nome.json"
    f.write_text(json.dumps(roteiro()), "utf-8")
    assert main([str(f)]) == 1
    assert "slug 'roman-myths' diferente do nome do arquivo 'outro-nome'" in capsys.readouterr().out


def test_entrada_nao_objeto():
    assert validar_roteiro(5) == ["roteiro deve ser um objeto JSON"]
    assert validar_roteiro([]) == ["roteiro deve ser um objeto JSON"]


def test_intro_e_outro_malformados():
    r = roteiro()
    r["intro"] = "texto"
    r["outro"] = None
    erros = validar_roteiro(r)
    assert any("intro: formato inválido" in e for e in erros)
    assert any("outro: formato inválido" in e for e in erros)


def test_travessao_nao_conta_como_palavra():
    r = roteiro()
    r["capitulos"][0]["trechos"][1]["narracao"] = "word " * 9 + "— " * 5
    r["capitulos"][0]["trechos"][2]["narracao"] = "word — " * 10
    assert erros_com("capítulo 1 trecho 2: narração com 9 palavras", r)
    assert not erros_com("capítulo 1 trecho 3", r)
    assert erros_com("capítulo 1: 199 palavras", r)  # 240 - 60 + 9 + 10


def test_hashtag_com_espaco_ou_so_cerquilha():
    r = roteiro()
    r["capitulos"][0]["short"]["hashtags"] = ["#history", "#ancient rome"]
    r["capitulos"][1]["short"]["hashtags"] = ["#history", "#"]
    assert erros_com("capítulo 1: hashtags", r)
    assert erros_com("capítulo 2: hashtags", r)


def test_short_curto_valido():
    r = roteiro()
    r["capitulos"][0]["short"] |= {"trechos": [1, 3, 8], "abertura": "This quote is fake.",
                                   "pergunta": "Which myth should I debunk next?"}
    assert validar_roteiro(r) == []


def test_short_curto_invalido():
    r = roteiro()
    r["capitulos"][0]["short"]["trechos"] = [3, 1]
    r["capitulos"][1]["short"]["trechos"] = [1, 9]
    r["capitulos"][2]["short"]["pergunta"] = " ".join(["word"] * 21)
    r["capitulos"][3]["short"]["abertura"] = ""
    assert erros_com("capítulo 1: short.trechos", r)
    assert erros_com("capítulo 2: short.trechos", r)
    assert erros_com("capítulo 3: short.pergunta", r)
    assert erros_com("capítulo 4: short.abertura", r)


def test_roteiro_sem_formato_usa_limites_antigos():
    r = roteiro()
    del r["formato"]
    assert erros_com("capítulo 1: 240 palavras (280–380)", r) and erros_com("intro: 40 palavras (85–130)", r)
    r["formato"] = 9
    assert erros_com("formato 9 desconhecido", r)


def test_formato_serie_pede_partes_de_ate_60_s():
    r = roteiro()
    r["formato"] = 3
    assert erros_com("capítulo 1: 240 palavras (95–120)", r)


def test_seta_so_na_linha_do_tempo():
    r = roteiro()
    r["intro"][0]["visual"] = {"tipo": "texto", "busca": "", "cena": "", "texto_tela": "509 BC → 1946", "mascote": ""}
    assert erros_com("intro trecho 1: texto_tela com '→'", r)

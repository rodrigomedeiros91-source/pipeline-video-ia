from fabrica import retencao


def test_ler_csv_porcentagem_com_cabecalho():
    texto = "Video position (%),Absolute audience retention (%)\n0,100%\n50,60%\n100,40%\n"
    assert retencao.ler_csv(texto) == [(0.0, 100.0), (50.0, 60.0), (100.0, 40.0)]


def test_ler_csv_fracoes_viram_porcentagem():
    assert retencao.ler_csv("0,1.05\n0.5,0.6\n1,0.4\n") == [(0.0, 105.0), (50.0, 60.0), (100.0, 40.0)]


def test_ler_srt():
    srt = "1\n00:00:00,000 --> 00:00:05,120\nYou've seen\nthese quotes.\n\n2\n00:01:01,500 --> 00:01:03,000\nNext.\n"
    assert retencao.ler_srt(srt) == [(0.0, 5.12, "You've seen these quotes."), (61.5, 63.0, "Next.")]


def test_analisar_gancho_quedas_e_ritmo():
    # vídeo de 100 s: 1 ponto por segundo, perde 30 pontos nos 10 primeiros e cai 5 de uma vez aos 60 s
    pontos = [(x, 100 - 3 * x if x <= 10 else 70 - 0.1 * (x - 10) - (5 if x > 60 else 0))
              for x in range(101)]
    r = retencao.analisar(pontos, 100)
    assert r["perda_gancho"] == 32.0  # 100 → 68 aos 30 s
    assert r["quedas"][0] == {"segundo": 60.0, "perda": 5.1}
    assert all(q["perda"] > retencao.QUEDA_MINIMA for q in r["quedas"])
    assert 0.1 <= r["ritmo"] < 0.2


def test_fala_em_e_relatorio():
    falas = [(55.0, 58.0, "Boring setup."), (59.0, 62.0, "Then a sponsor."), (90.0, 95.0, "End.")]
    assert retencao.fala_em(falas, 60) == "Boring setup. Then a sponsor."
    r = {"inicio": 100, "fim": 40, "perda_gancho": 20.0, "quedas": [{"segundo": 60, "perda": 5.0}],
         "ritmo": 0.3}
    texto = retencao.relatorio(r, falas)
    assert "[saudável]" in texto and '1:00  "Boring setup. Then a sponsor."' in texto


def test_main_usa_legenda_do_slug(tmp_path, capsys):
    (tmp_path / "videos" / "x").mkdir(parents=True)
    (tmp_path / "videos" / "x" / "legendas.srt").write_text(
        "1\n00:00:00,000 --> 00:01:40,000\nTudo.\n", "utf-8")
    csv = tmp_path / "r.csv"
    csv.write_text("\n".join(f"{x},{100 - x / 2}" for x in range(0, 101, 10)), "utf-8")
    assert retencao.main([str(csv), "--slug", "x"], base=tmp_path) == 0
    assert "GANCHO" in capsys.readouterr().out
    assert retencao.main([str(csv)], base=tmp_path) == 2  # sem duração

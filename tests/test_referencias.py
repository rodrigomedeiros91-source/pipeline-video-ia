from fabrica import referencias


def v(canal, views, titulo="T", dur=600):
    return {"channel_id": canal, "channel": canal.upper(), "view_count": views, "title": titulo,
            "duration": dur, "url": f"https://youtu.be/{canal}"}


def test_fora_da_curva_usa_a_mediana_do_proprio_canal():
    videos = [v("grande", 400_000, "normal"), v("pequeno", 90_000, "estouro"), v("novo", 1_000_000)]
    views = {"grande": [400_000] * 5, "pequeno": [30_000] * 5, "novo": [10, 20]}
    linhas, ignorados = referencias.fora_da_curva(videos, views, 1.5)
    assert [(r["titulo"], r["multiplo"]) for r in linhas] == [("estouro", 3.0)]
    assert ignorados == ["NOVO"]


def test_tabela_escapa_barra_vertical():
    linhas, _ = referencias.fora_da_curva([v("c", 300, "A | B", 125)], {"c": [100] * 4}, 1)
    t = referencias.tabela(linhas)
    assert "| 3.0x | 300 | 100 | 2:05 | C | [A / B](https://youtu.be/c) |" in t


def test_main_com_buscas_falsas(capsys):
    def buscar(busca, n):
        return [v("c", 500, "hit"), v("ruim", 100)]

    def views_do_canal(canal, n):
        if canal == "ruim":
            raise RuntimeError("falhou")
        return [100] * 5
    assert referencias.main(["tema"], buscar=buscar, views_do_canal=views_do_canal) == 0
    out = capsys.readouterr().out
    assert "5.0x" in out and "RUIM" in out

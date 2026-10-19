import json

from fabrica import youtube


def pacote():
    return {"slug": "x", "longo": {"arquivo": "v.mp4", "titulo": "Longo", "descricao": "d.txt",
                                   "legendas": "l.srt", "thumbnail": "t.jpg", "data": "2026-10-17",
                                   "hora": "16:00", "playlist": "Lista", "status": "pendente", "url": ""},
            "shorts": [{"n": 2, "arquivo": "s2.mp4", "titulo": "S2", "descricao_youtube": "ver {link_longo}",
                        "data": "2026-10-18", "hora": "13:00", "status": "pendente", "url": ""},
                       {"n": 1, "arquivo": "s1.mp4", "titulo": "S1", "descricao_youtube": "ver {link_longo}",
                        "data": "2026-10-17", "hora": "20:00", "status": "agendado", "url": "u"}]}


def test_descricao_longo_tira_title_e_tags():
    corpo, tags = youtube.descricao_longo("TITLE: X\n\nTexto.\n\nTAGS: history, myths , \n")
    assert corpo == "Texto." and tags == ["history", "myths"]


def test_meta_agenda_no_horario_de_brasilia():
    m = youtube.meta({"titulo": "T", "data": "2026-10-17", "hora": "16:00"}, "d", ["a"], "Lista")
    assert m["publishAt"] == "2026-10-17T16:00:00-03:00"
    assert m["privacyStatus"] == "private" and m["madeForKids"] is False
    assert m["containsSyntheticMedia"] is True and m["playlistTitles"] == ["Lista"]
    assert "playlistTitles" not in youtube.meta({"titulo": "T", "data": "d", "hora": "h"}, "d")


def test_meta_agora_publica_sem_agendar():
    m = youtube.meta({"titulo": "T", "data": "2026-10-18", "hora": "agora"}, "d")
    assert m["privacyStatus"] == "public" and "publishAt" not in m


def test_fila_pula_agendados_e_respeita_so():
    pac = pacote()
    assert [r for r, _ in youtube.fila(pac)] == ["longo", "Short 2"]
    assert [r for r, _ in youtube.fila(pac, [2])] == ["Short 2"]


def preparar(tmp_path):
    base = tmp_path / "historia"
    (base / "shorts" / "x").mkdir(parents=True)
    (tmp_path / "d.txt").write_text("TITLE: Longo\nCorpo.\nTAGS: a, b\n", "utf-8")
    caminho = base / "shorts" / "x" / "publicacao.json"
    caminho.write_text(json.dumps(pacote()), "utf-8")
    return base, caminho


def test_main_envia_longo_e_troca_link_nos_shorts(tmp_path, monkeypatch):
    base, caminho = preparar(tmp_path)
    monkeypatch.setattr(youtube, "FERRAMENTA", tmp_path)
    (tmp_path / "client_secrets.json").write_text("{}")
    (tmp_path / "request.token").write_text("{}")
    chamadas = []

    def enviar(arquivo, dados, **extras):
        chamadas.append((arquivo.name, dados["description"], extras))
        return f"id{len(chamadas)}"
    assert youtube.main(["x"], base=base, raiz=tmp_path, enviar=enviar) == 0
    assert chamadas[0] == ("v.mp4", "Corpo.", {"thumbnail": tmp_path / "t.jpg", "legenda": tmp_path / "l.srt"})
    assert chamadas[1][:2] == ("s2.mp4", "ver https://youtu.be/id1")
    pac = json.loads(caminho.read_text("utf-8"))
    assert pac["longo"]["status"] == "agendado" and pac["shorts"][0]["url"] == "https://youtu.be/id2"


def test_main_para_no_erro_e_guarda_o_que_ja_foi(tmp_path, monkeypatch):
    base, caminho = preparar(tmp_path)
    monkeypatch.setattr(youtube, "FERRAMENTA", tmp_path)
    (tmp_path / "client_secrets.json").write_text("{}")
    (tmp_path / "request.token").write_text("{}")

    def enviar(arquivo, dados, **extras):
        if arquivo.name == "s2.mp4":
            raise RuntimeError("quotaExceeded")
        return "id1"
    assert youtube.main(["x"], base=base, raiz=tmp_path, enviar=enviar) == 1
    pac = json.loads(caminho.read_text("utf-8"))
    assert pac["longo"]["status"] == "agendado" and pac["shorts"][0]["status"] == "pendente"


def test_main_short_sem_link_do_longo_e_teste(tmp_path, monkeypatch, capsys):
    base, _ = preparar(tmp_path)
    monkeypatch.setattr(youtube, "FERRAMENTA", tmp_path)
    assert youtube.main(["x"], base=base, raiz=tmp_path, enviar=None) == 2  # sem client_secrets.json
    (tmp_path / "client_secrets.json").write_text("{}")
    (tmp_path / "request.token").write_text("{}")
    assert youtube.main(["x", "--so", "2"], base=base, raiz=tmp_path, enviar=None) == 1
    assert youtube.main(["x", "--teste"], base=base, raiz=tmp_path, enviar=None) == 0
    assert "2026-10-17T16:00:00-03:00" in capsys.readouterr().out


def test_url_login_pede_os_escopos_e_o_estado():
    cliente = {"auth_uri": "https://accounts.google.com/o/oauth2/auth", "client_id": "abc",
               "redirect_uris": ["http://localhost:8080/oauth2callback"]}
    url = youtube.url_login(cliente, "xyz")
    assert url.startswith("https://accounts.google.com/o/oauth2/auth?client_id=abc")
    assert "state=xyz" in url and "access_type=offline" in url and "youtube.upload" in url


def test_token_go_no_formato_do_youtubeuploader():
    import datetime as dt
    agora = dt.datetime(2026, 10, 12, 3, 0, tzinfo=dt.timezone.utc)
    t = youtube.token_go({"access_token": "a", "refresh_token": "r", "expires_in": 3599}, agora)
    assert t == {"access_token": "a", "token_type": "Bearer", "refresh_token": "r",
                 "expiry": "2026-10-12T03:59:59+00:00"}


def test_login_valido_vence_em_menos_de_7_dias(tmp_path):
    import os
    token = tmp_path / "request.token"
    assert not youtube.login_valido(token)
    token.write_text("{}")
    os.utime(token, (1000, 1000))
    assert youtube.login_valido(token, agora=1000 + 6 * 86400)
    assert not youtube.login_valido(token, agora=1000 + 7 * 86400)

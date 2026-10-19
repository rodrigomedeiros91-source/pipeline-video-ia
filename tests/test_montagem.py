from fabrica import montagem
from tests.test_roteiro import roteiro


def p(ini, fim):
    return {"texto": "w", "inicio": ini, "fim": fim}


def test_blocos():
    bls = montagem.blocos(roteiro())
    assert [b["id"] for b in bls] == ["intro", "1", "2", "3", "4", "5", "6", "outro"]
    assert [i for i, _ in bls[0]["trechos"]] == ["intro.1", "intro.2"]
    assert bls[1]["trechos"][0][0] == "1.1" and len(bls[1]["trechos"]) == 8
    assert bls[1]["titulo"] == "Gladiators" and bls[1]["short"]["titulo"] == "Myth #Shorts"
    assert (bls[0]["titulo"], bls[0]["short"]) == ("Intro", None)
    assert (bls[-1]["titulo"], bls[-1]["short"]) == ("Outro", None)


def test_texto_do_bloco():
    bloco = {"trechos": [("intro.1", {"narracao": "Hello there."}), ("intro.2", {"narracao": "Bye."})]}
    assert montagem.texto_do_bloco(bloco) == "Hello there. Bye."


def test_fronteiras_no_meio_da_pausa():
    palavras = [p(0.0, 0.5), p(0.5, 1.0), p(1.5, 2.0), p(2.0, 2.5)]
    assert montagem.fronteiras(palavras, ["a b", "c d"], 3.0) == ([(0.0, 1.25), (1.25, 3.0)], False)


def test_fronteiras_proporcional_quando_nao_bate():
    assert montagem.fronteiras([p(0, 1)] * 3, ["aa", "aaaaaa"], 8.0) == ([(0.0, 2.0), (2.0, 8.0)], True)


def test_linha_do_tempo():
    narrados = [
        {"id": "intro", "titulo": "Intro", "short": None, "dur": 3.0,
         "trechos": [("intro.1", 0.0, 1.25), ("intro.2", 1.25, 3.0)]},
        {"id": "1", "titulo": "Cake", "short": {"x": 1}, "dur": 4.0, "trechos": [("1.1", 0.0, 4.0)]},
        {"id": "outro", "titulo": "Outro", "short": None, "dur": 1.0, "trechos": [("outro.1", 0.0, 1.0)]},
    ]
    eventos, caps, total = montagem.linha_do_tempo(narrados)
    assert total == 10.0
    assert [e["id"] for e in eventos] == ["intro.1", "intro.2", "cartao.1", "1.1", "outro.1"]
    assert [e["quadros"] for e in eventos] == [38, 52, 60, 120, 30]
    assert caps == [
        {"id": "intro", "titulo": "Intro", "inicio": 0.0, "inicio_narracao": 0.0, "fim": 3.0, "short": None},
        {"id": "1", "titulo": "Cake", "inicio": 3.0, "inicio_narracao": 5.0, "fim": 9.0, "short": {"x": 1}},
        {"id": "outro", "titulo": "Outro", "inicio": 9.0, "inicio_narracao": 9.0, "fim": 10.0, "short": None},
    ]


def test_linha_do_tempo_sem_deriva():
    trechos = [(f"1.{i}", i * 1.0333, (i + 1) * 1.0333) for i in range(80)]
    narrados = [{"id": "1", "titulo": "X", "short": None, "dur": 80 * 1.0333, "trechos": trechos}]
    eventos, _, total = montagem.linha_do_tempo(narrados)
    assert sum(e["quadros"] for e in eventos) == round(total * 30)


def test_narrar_bloco_usa_cache(tmp_path, monkeypatch):
    chamadas, clientes = [], []

    def narrar(cliente, texto, destino, voice_id, idioma):
        chamadas.append((cliente, texto, voice_id, idioma))
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(b"MP3")
        return [{"texto": "a", "inicio": 0.0, "fim": 0.2}]

    monkeypatch.setattr(montagem.audio, "narrar", narrar)
    monkeypatch.setattr(montagem.clipes, "para_wav", lambda mp3, wav: wav.write_bytes(b"WAV"))

    def obter():
        clientes.append(1)
        return "cliente"

    bloco = {"id": "intro", "trechos": [("intro.1", {"narracao": "Hello there."}),
                                        ("intro.2", {"narracao": "Bye."})]}
    wav, palavras = montagem.narrar_bloco(obter, tmp_path, bloco, "voz1")
    assert chamadas == [("cliente", "Hello there. Bye.", "voz1", "en")]
    assert palavras == [{"texto": "a", "inicio": 0.0, "fim": 0.2}] and wav.read_bytes() == b"WAV"
    montagem.narrar_bloco(obter, tmp_path, bloco, "voz1")
    assert len(chamadas) == 1 and len(clientes) == 1
    montagem.narrar_bloco(obter, tmp_path, bloco, "voz2")
    assert len(chamadas) == 2


def test_infos_usa_animacao_tambem_em_texto(tmp_path):
    v = {"tipo": "texto", "texto_tela": "TROLL-O-METER: 5/5", "mascote": "rindo"}
    roteiro = {"intro": [{"visual": v}, {"visual": v}], "capitulos": [], "outro": []}
    manifesto = {"trechos": [{"id": "intro.1"}, {"id": "intro.2"}]}
    anim = tmp_path / "visual" / "s" / "imagens" / "intro.1-anim.mp4"
    anim.parent.mkdir(parents=True)
    anim.write_bytes(b"")
    inf = montagem.infos(roteiro, manifesto, tmp_path, "s")
    assert inf["intro.1"]["animacao"] == str(anim)
    assert "animacao" not in inf["intro.2"]

from fabrica.__main__ import checar_ambiente, gerar_relatorio

MOMENTO = {"inicio": 100.0, "fim": 160.0, "tema": "easter_egg", "motivo": "m", "score_viral": 90}
RECEITA = {
    "tema": "easter_egg", "score": 88, "fiel_ao_contexto": True,
    "alertas": ["checar versão do patch"],
    "en": {"titulo": "Secret Room #Shorts", "tiktok_legenda": "Nobody found this",
           "hashtags": ["#zelda", "#easteregg"], "produto": "Zelda Twilight Princess HD"},
    "pt": {"titulo": "Sala Secreta #Shorts", "tiktok_legenda": "Ninguém achou isso",
           "hashtags": ["#zelda", "#segredo"], "produto": "Zelda Twilight Princess HD Wii U"},
    "blocos": [
        {"tipo": "narracao", "en": "Look here", "pt": "Olha aqui", "inicio": 100.0, "fim": 0,
         "legenda_en": "", "legenda_pt": ""},
        {"tipo": "original", "en": "", "pt": "", "inicio": 100.0, "fim": 110.0,
         "legenda_en": "x", "legenda_pt": "x"},
    ],
}


def test_checar_ambiente_lista_faltantes(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda nome: None)
    for v in ("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICES_EN",
              "ELEVENLABS_VOICES_PT"):
        monkeypatch.delenv(v, raising=False)
    assert checar_ambiente() == ["ffmpeg", "ffprobe", "ANTHROPIC_API_KEY",
                                 "ELEVENLABS_API_KEY", "ELEVENLABS_VOICES_EN",
                                 "ELEVENLABS_VOICES_PT"]


def test_relatorio_por_idioma_pronto_para_upload():
    itens = [
        {"n": 1, "status": "pronto", "momento": MOMENTO, "receita": RECEITA,
         "arquivo": "01_pronto_sala-secreta-shorts.mp4", "duracao": 74.0, "pct_narracao": 0.47,
         "voz": "lucas", "alertas": ["abaixo de 60 s: não monetiza no TikTok"]},
        {"n": 2, "status": "descartado", "momento": MOMENTO, "receita": None,
         "motivo": "[pt] duração estimada 40 s; precisa ficar entre 61 e 90 s"},
    ]
    md = gerar_relatorio("guia", "Canal X", "pt", itens)
    assert "# Relatório — guia [PT]" in md
    assert "Fonte: Canal X" in md
    assert "## 🟢 01 — Sala Secreta #Shorts" in md
    assert "74s | Narração: 47% | Voz: lucas" in md
    assert "**YouTube:** Sala Secreta #Shorts" in md
    assert "**TikTok:** Ninguém achou isso #zelda #segredo" in md
    assert "**Produto:** Zelda Twilight Princess HD Wii U" in md
    assert "> 🎙️ Olha aqui" in md
    assert "> 🎬 original 100.0s–110.0s" in md
    assert "⚠️ checar versão do patch" in md
    assert "⚠️ abaixo de 60 s: não monetiza no TikTok" in md
    assert "## 🔴 02 — (sem título)" in md
    assert "Motivo: [pt] duração estimada 40 s" in md

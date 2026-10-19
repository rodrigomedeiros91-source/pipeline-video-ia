"""Banco visual do canal de história: acervo, cenas e poses de cada trecho do roteiro."""
import argparse
import html
import json
import os
import sys
from http.client import HTTPException
from pathlib import Path

from fabrica import cenas, commons, salvar_json
from fabrica.roteiro import validar_roteiro

BASE = Path(__file__).resolve().parent.parent / "historia"
CAMPOS_CREDITO = ("titulo", "autor", "licenca", "url_licenca", "pagina")


def listar_trechos(roteiro):
    """[(id, trecho)] na ordem do vídeo: intro.N, C.N, outro.N (N a partir de 1)."""
    trechos = [(f"intro.{i}", t) for i, t in enumerate(roteiro["intro"], 1)]
    for c, cap in enumerate(roteiro["capitulos"], 1):
        trechos += [(f"{c}.{i}", t) for i, t in enumerate(cap["trechos"], 1)]
    return trechos + [(f"outro.{i}", t) for i, t in enumerate(roteiro["outro"], 1)]


def _apagar(pasta, id_):
    for f in (pasta / "imagens").glob(f"{id_}-*"):
        f.unlink()


def _refazer_cena(id_, visual, ant, regerar):
    return id_ in regerar or bool(ant and (ant["tipo"] != "cena" or ant.get("cena") != visual["cena"]))


def _quadros(id_):
    return [f"imagens/{id_}-q{k}.png" for k in range(1, cenas.POSES_CENA + 1)]


def cenas_pendentes(roteiro, anterior, pasta, regerar):
    """Quantas imagens a OpenAI vai gerar nesta rodada."""
    n = 0
    for id_, t in listar_trechos(roteiro):
        v = t["visual"]
        if v["tipo"] != "cena":
            continue
        quadros = _quadros(id_)
        if _refazer_cena(id_, v, anterior.get(id_), regerar) or not (pasta / quadros[0]).exists():
            n += cenas.POSES_CENA
        else:
            n += sum(not (pasta / q).exists() for q in quadros[1:])
    return n


def _acervo(id_, v, ant, pasta, http, faltas):
    if (ant and ant.get("busca") == v["busca"] and ant.get("opcoes")
            and all((pasta / o["arquivo"]).exists() for o in ant["opcoes"])):
        return {"escolhida": ant["escolhida"], "opcoes": ant["opcoes"]}
    _apagar(pasta, id_)
    opcoes = []
    try:
        for letra, o in zip("ABCD", commons.buscar(v["busca"], v["tipo"], http)):
            arquivo = f"imagens/{id_}-{letra}{commons.extensao(o['url'])}"
            commons.baixar(o["url"], pasta / arquivo, http)
            opcoes.append({"letra": letra, "arquivo": arquivo} | {k: o[k] for k in CAMPOS_CREDITO})
    except (OSError, ValueError, HTTPException) as e:
        faltas.append({"id": id_, "motivo": f"erro na Commons: {e}"})
        return {"escolhida": "", "opcoes": []}
    if not opcoes:
        faltas.append({"id": id_, "motivo": f"sem imagem livre para '{v['busca']}'"})
    return {"escolhida": "A" if opcoes else "", "opcoes": opcoes}


def _cena(id_, v, ant, pasta, poses, regerar, cliente, faltas):
    quadros = _quadros(id_)
    q1 = quadros[0]
    if _refazer_cena(id_, v, ant, regerar):
        _apagar(pasta, id_)
    try:
        if not (pasta / q1).exists():
            for q in quadros[1:]:
                (pasta / q).unlink(missing_ok=True)
            refs = [poses / f"{p}.webp" for p in cenas.REFS]
            cenas.gerar_quadro1(cliente, v["cena"], refs, pasta / q1)
        for k, q in enumerate(quadros[1:], 2):
            if not (pasta / q).exists():
                cenas.gerar_pose(cliente, pasta / q1, pasta / q, k)
    except Exception as e:  # recusa de conteúdo, rede ou API: registra e segue para o próximo
        faltas.append({"id": id_, "motivo": f"erro ao gerar cena: {e}"})
    return [q for q in quadros if (pasta / q).exists()]


def _mascote(id_, pose, pasta, poses, faltas):
    if not pose:
        return {"mascote": "", "mascote_arquivo": ""}
    arquivo = poses / f"{pose}.webp"
    if not arquivo.exists():
        faltas.append({"id": id_, "motivo": f"pose '{pose}' não encontrada"})
        return {"mascote": pose, "mascote_arquivo": ""}
    return {"mascote": pose, "mascote_arquivo": Path(os.path.relpath(arquivo, pasta)).as_posix()}


def montar(roteiro, pasta, poses, anterior, trocar, regerar, http, cliente):
    """Manifesto do roteiro, reaproveitando o que não mudou desde o manifesto anterior."""
    trechos_lista = listar_trechos(roteiro)
    trechos, faltas = [], []
    for id_, t in trechos_lista:
        v, ant = t["visual"], anterior.get(id_)
        if ant and ant["tipo"] != v["tipo"]:
            _apagar(pasta, id_)
            ant = None
        e = {"id": id_, "tipo": v["tipo"]}
        if v["tipo"] in ("acervo", "mapa"):
            e["busca"] = v["busca"]
            e |= _acervo(id_, v, ant, pasta, http, faltas)
            if trocar.get(id_) in [o["letra"] for o in e["opcoes"]]:
                e["escolhida"] = trocar[id_]
        elif v["tipo"] == "cena":
            e["cena"] = v["cena"]
            e["quadros"] = _cena(id_, v, ant, pasta, poses, regerar, cliente, faltas)
        e |= _mascote(id_, v["mascote"], pasta, poses, faltas)
        trechos.append(e)

    # Limpa imagens de trechos que não existem mais no roteiro
    ids_validos = {id_ for id_, _ in trechos_lista}
    imagens_dir = pasta / "imagens"
    if imagens_dir.exists():
        for f in imagens_dir.glob("*"):
            if f.is_file():
                id_do_arquivo = f.name.rsplit("-", 1)[0]
                if id_do_arquivo not in ids_validos:
                    f.unlink()

    return {"slug": roteiro["slug"], "trechos": trechos, "faltas": faltas}


def creditos(manifesto):
    """Créditos das imagens escolhidas, na ordem do vídeo, sem repetir arquivo."""
    linhas, vistas = ["Images from Wikimedia Commons:"], set()
    for e in manifesto["trechos"]:
        op = next((o for o in e.get("opcoes", []) if o["letra"] == e.get("escolhida")), None)
        if not op or op["pagina"] in vistas:
            continue
        vistas.add(op["pagina"])
        licenca = f"{op['licenca']} ({op['url_licenca']})" if op["url_licenca"] else op["licenca"]
        linhas.append(f'- "{op["titulo"]}" by {op["autor"]}, {licenca} — {op["pagina"]}')
    linhas += ["", "Illustrations and mascot: original artwork for this channel."]
    return "\n".join(linhas) + "\n"


CSS = ("body{font-family:sans-serif;margin:24px;background:#fafafa}"
       ".trecho{background:#fff;border:2px solid #ddd;border-radius:8px;padding:12px;margin:12px 0}"
       ".falta{border-color:#d00}.motivo{color:#d00;font-weight:bold}"
       "figure{display:inline-block;margin:4px;vertical-align:top}figcaption{font-size:12px}")


def revisao(manifesto, narracoes):
    """Folha de revisão estática: escolhida em destaque, alternativas, quadros e pose."""
    esc = html.escape
    slug = manifesto["slug"]
    motivos = {}
    for f in manifesto["faltas"]:
        motivos.setdefault(f["id"], []).append(f["motivo"])
    partes = [f"<!doctype html><html><head><meta charset='utf-8'><title>Revisão — {esc(slug)}"
              f"</title><style>{CSS}</style></head><body>",
              f"<h1>{esc(slug)}</h1>",
              f"<p>{len(manifesto['trechos'])} trechos, {len(manifesto['faltas'])} faltas</p>",
              f"<p>Ajustes: <code>python -m fabrica.visual {esc(slug)} --trocar 3.4=B</code> · "
              f"<code>python -m fabrica.visual {esc(slug)} --regerar 5.1</code></p>"]
    for e in manifesto["trechos"]:
        falta = motivos.get(e["id"], [])
        texto = " ".join(narracoes.get(e["id"], "").split()[:12])
        partes.append(f"<section class='trecho{' falta' if falta else ''}'>"
                      f"<h2>{esc(e['id'])} · {esc(e['tipo'])}</h2><p>{esc(texto)}…</p>")
        partes += [f"<p class='motivo'>{esc(m)}</p>" for m in falta]
        for o in e.get("opcoes", []):
            escolhida = o["letra"] == e.get("escolhida")
            partes.append(f"<figure><img src='{esc(o['arquivo'])}' width='{480 if escolhida else 240}'>"
                          f"<figcaption>{esc(o['letra'])}{' (escolhida)' if escolhida else ''} · "
                          f"{esc(o['licenca'])} · <a href='{esc(o['pagina'])}'>Commons</a>"
                          f"</figcaption></figure>")
        for i, q in enumerate(e.get("quadros", []), 1):
            partes.append(f"<figure><img src='{esc(q)}' width='480'>"
                          f"<figcaption>quadro {i}</figcaption></figure>")
        if e.get("mascote_arquivo"):
            partes.append(f"<figure><img src='{esc(e['mascote_arquivo'])}' width='120'>"
                          f"<figcaption>{esc(e['mascote'])}</figcaption></figure>")
        partes.append("</section>")
    partes.append("</body></html>")
    return "\n".join(partes)


def _cliente_openai():
    from openai import OpenAI
    return OpenAI()


def _ler_manifesto(caminho):
    if not caminho.exists():
        return {}
    return {e["id"]: e for e in json.loads(caminho.read_text("utf-8"))["trechos"]}


def main(argv=None, base=BASE, http=commons.http_padrao, criar_cliente=_cliente_openai):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m fabrica.visual",
                                 description="Banco visual de um roteiro do canal de história")
    ap.add_argument("slug")
    ap.add_argument("--trocar", action="append", default=[], metavar="ID=LETRA")
    ap.add_argument("--regerar", action="append", default=[], metavar="ID")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0

    caminho = base / "roteiros" / f"{args.slug}.json"
    try:
        roteiro = json.loads(caminho.read_text("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        print(f"erro ao ler {caminho}: {e}")
        return 2
    erros = validar_roteiro(roteiro)
    if erros:
        print("roteiro inválido (rode python -m fabrica.roteiro):\n" + "\n".join(erros))
        return 2
    if roteiro["slug"] != args.slug:
        print(f"slug '{roteiro['slug']}' diferente do nome do arquivo '{args.slug}'")
        return 2

    pasta = base / "visual" / args.slug
    anterior = _ler_manifesto(pasta / "manifesto.json")
    trechos = listar_trechos(roteiro)
    tipos = {id_: t["visual"]["tipo"] for id_, t in trechos}
    trocar = {}
    for item in args.trocar:
        id_, _, letra = item.partition("=")
        letras = [o["letra"] for o in anterior.get(id_, {}).get("opcoes", [])]
        if letra not in letras:
            print(f"--trocar {item}: o trecho {id_} não tem a opção '{letra}' "
                  f"(opções: {', '.join(letras) or 'nenhuma'})")
            return 2
        trocar[id_] = letra
    for id_ in args.regerar:
        if tipos.get(id_) != "cena":
            print(f"--regerar {id_}: não é um trecho de cena")
            return 2
    regerar = set(args.regerar)

    cliente = None
    pendentes = cenas_pendentes(roteiro, anterior, pasta, regerar)
    if pendentes:
        if not os.environ.get("OPENAI_API_KEY"):
            print("Faltando OPENAI_API_KEY no .env (necessária para gerar as cenas).")
            return 2
        print(f"{pendentes} imagens a gerar (~US$ {pendentes * cenas.CUSTO_IMAGEM:.2f})")
        cliente = criar_cliente()

    manifesto = montar(roteiro, pasta, base / "mascote" / "poses", anterior, trocar, regerar,
                       http, cliente)
    salvar_json(pasta / "manifesto.json", manifesto)
    (pasta / "creditos.txt").write_text(creditos(manifesto), "utf-8")
    narracoes = {id_: t["narracao"] for id_, t in trechos}
    (pasta / "revisao.html").write_text(revisao(manifesto, narracoes), "utf-8")
    print(f"{len(manifesto['trechos'])} trechos, {len(manifesto['faltas'])} faltas → "
          f"{pasta / 'revisao.html'}")
    for f in manifesto["faltas"]:
        print(f"  {f['id']}: {f['motivo']}")
    return 1 if manifesto["faltas"] else 0


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    sys.exit(main())

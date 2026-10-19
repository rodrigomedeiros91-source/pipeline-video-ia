"""Envia e agenda no YouTube, sem navegador, o vídeo longo e os Shorts pendentes do publicacao.json.

Usa o youtubeuploader (https://github.com/porjo/youtubeuploader, Apache-2.0), que fica fora do git em
ferramentas/youtubeuploader/ junto com client_secrets.json e request.token (o login do canal).
"""
import argparse
import datetime as dt
import http.server
import json
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

from fabrica import montagem, salvar_json

RAIZ = montagem.BASE.parent  # caminhos do publicacao.json são relativos a "Fábrica de Cortes/"
FERRAMENTA = RAIZ / "ferramentas" / "youtubeuploader"
# shortcut: horário de Brasília fixo em -03:00 (sem horário de verão desde 2019); se voltar, usar zoneinfo
FUSO = "-03:00"
CATEGORIA = "27"  # Educação
SELO_IA = True  # voz e cenas geradas por IA: marca "conteúdo alterado ou sintético"
# Login sempre no Google Chrome (decisão do Rodrigo): o youtubeuploader abriria o navegador padrão do Windows.
CHROME = Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe")
ESCOPOS = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtubepartner",
           "https://www.googleapis.com/auth/youtube"]  # os mesmos do youtubeuploader
VALIDADE_LOGIN = 6.5 * 86400  # app em modo "Teste" no Google: o login vence em 7 dias


def url_login(cliente, estado):
    return cliente["auth_uri"] + "?" + urllib.parse.urlencode({
        "client_id": cliente["client_id"], "redirect_uri": cliente["redirect_uris"][0], "response_type": "code",
        "scope": " ".join(ESCOPOS), "access_type": "offline", "prompt": "consent", "state": estado})


def token_go(resposta, agora):
    """Resposta do Google → JSON no formato oauth2.Token que o youtubeuploader lê do request.token."""
    expira = agora + dt.timedelta(seconds=int(resposta.get("expires_in", 3600)))
    return {"access_token": resposta["access_token"], "token_type": resposta.get("token_type", "Bearer"),
            "refresh_token": resposta["refresh_token"], "expiry": expira.isoformat()}


def login(espera=600):
    """Abre o consentimento do Google no Chrome, recebe o código em localhost:8080 e grava request.token."""
    cliente = json.loads((FERRAMENTA / "client_secrets.json").read_text("utf-8"))["web"]
    estado, recebido = secrets.token_urlsafe(16), {}

    class Retorno(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            recebido.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Login feito. Pode fechar esta aba.".encode("utf-8"))

        def log_message(self, *a):
            pass

    porta = urllib.parse.urlparse(cliente["redirect_uris"][0]).port or 8080
    with http.server.HTTPServer(("localhost", porta), Retorno) as srv:
        srv.timeout = espera
        subprocess.Popen([str(CHROME), url_login(cliente, estado)])
        print("Abri o login do Google no Chrome: escolha o canal The Myth Troll e clique em Permitir.", flush=True)
        srv.handle_request()
    if recebido.get("state") != estado or "code" not in recebido:
        raise RuntimeError(f"login não concluído: {recebido.get('error', 'sem resposta')}")
    corpo = urllib.parse.urlencode({"code": recebido["code"], "client_id": cliente["client_id"],
                                    "client_secret": cliente["client_secret"], "grant_type": "authorization_code",
                                    "redirect_uri": cliente["redirect_uris"][0]}).encode()
    with urllib.request.urlopen(urllib.request.Request(cliente["token_uri"], data=corpo)) as r:
        resposta = json.loads(r.read())
    (FERRAMENTA / "request.token").write_text(json.dumps(token_go(resposta, dt.datetime.now(dt.timezone.utc))), "utf-8")
    print("Login salvo.")


def login_valido(token, agora=None):
    return token.exists() and (agora or time.time()) - token.stat().st_mtime < VALIDADE_LOGIN


def descricao_longo(texto):
    """(descrição sem as linhas TITLE:/TAGS:, lista de tags)."""
    linhas = texto.strip().splitlines()
    tags = [t.strip() for l in linhas if l.startswith("TAGS:") for t in l[5:].split(",") if t.strip()]
    corpo = "\n".join(l for l in linhas if not l.startswith(("TITLE:", "TAGS:"))).strip()
    return corpo, tags


def meta(item, descricao, tags=(), playlist=""):
    m = {"title": item["titulo"], "description": descricao, "tags": list(tags),
         "privacyStatus": "private", "publishAt": f"{item['data']}T{item['hora']}:00{FUSO}",
         "madeForKids": False, "categoryId": CATEGORIA, "language": "en",
         "containsSyntheticMedia": SELO_IA}
    if item["hora"] == "agora":  # publica na hora, público (sem agendamento)
        m["privacyStatus"] = "public"
        del m["publishAt"]
    if playlist:
        m["playlistTitles"] = [playlist]
    return m


def fila(pac, so=()):
    """[(rótulo, item)] pendentes, na ordem: longo, depois Shorts por n."""
    itens = [("longo", pac["longo"])] if not so else []
    itens += [(f"Short {s['n']}", s) for s in sorted(pac["shorts"], key=lambda s: s["n"])
              if not so or s["n"] in so]
    return [(r, i) for r, i in itens if i.get("status", "pendente") == "pendente"]


def enviar(arquivo, dados, thumbnail="", legenda=""):
    """Roda o youtubeuploader e devolve o id do vídeo (RuntimeError com o motivo se falhar)."""
    with tempfile.TemporaryDirectory() as tmp:
        entrada, saida = Path(tmp) / "meta.json", Path(tmp) / "saida.json"
        entrada.write_text(json.dumps(dados, ensure_ascii=False), "utf-8")
        cmd = [str(FERRAMENTA / "youtubeuploader.exe"), "-filename", str(arquivo), "-metaJSON", str(entrada),
               "-metaJSONout", str(saida), "-quiet"]
        if thumbnail:
            cmd += ["-thumbnail", str(thumbnail)]
        if legenda:
            cmd += ["-caption", str(legenda)]
        r = subprocess.run(cmd, cwd=FERRAMENTA, capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        erro = (r.stderr or r.stdout).strip()[-500:]
        if not saida.exists():  # o vídeo não subiu
            raise RuntimeError(erro or "sem resposta do youtubeuploader")
        if r.returncode:  # o vídeo subiu; falhou thumbnail, legenda ou playlist (não reenviar!)
            print(f"  aviso: vídeo enviado, mas: {erro}")
        return json.loads(saida.read_text("utf-8"))["id"]


def main(argv=None, base=montagem.BASE, raiz=RAIZ, enviar=enviar):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m fabrica.youtube",
                                 description="Envia e agenda no YouTube os itens pendentes do publicacao.json")
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--login", action="store_true", help="refaz o login do canal no Chrome")
    ap.add_argument("--so", type=int, nargs="+", default=[], metavar="N", help="só estes Shorts (ex.: --so 1)")
    ap.add_argument("--teste", action="store_true", help="mostra o que seria enviado, sem enviar")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0

    if args.login or not args.slug:
        if not args.slug and not args.login:
            print("Informe o slug (ou --login).")
            return 2
        try:
            login()
        except (OSError, RuntimeError, KeyError) as e:
            print(f"Login falhou: {e}")
            return 1
        if not args.slug:
            return 0
    caminho = base / "shorts" / args.slug / "publicacao.json"
    if not caminho.exists():
        print(f"Não achei {caminho}. Rode antes: python -m fabrica.shorts {args.slug}")
        return 2
    if not args.teste and not (FERRAMENTA / "client_secrets.json").exists():
        print(f"Falta {FERRAMENTA / 'client_secrets.json'} (configuração do Google, uma vez só).")
        return 2
    if not args.teste and not login_valido(FERRAMENTA / "request.token"):
        try:  # sem login válido o youtubeuploader abriria o navegador padrão e travaria esperando
            login()
        except (OSError, RuntimeError, KeyError) as e:
            print(f"Login falhou: {e}")
            return 1
    pac = json.loads(caminho.read_text("utf-8"))
    pendentes = fila(pac, args.so)
    if not pendentes:
        print("Nada pendente.")
        return 0
    for rotulo, item in pendentes:
        if rotulo == "longo":
            descricao, tags = descricao_longo((raiz / item["descricao"]).read_text("utf-8"))
            dados = meta(item, descricao, tags, item.get("playlist", ""))
            extras = {"thumbnail": raiz / item["thumbnail"] if item.get("thumbnail") else "",
                      "legenda": raiz / item["legendas"] if item.get("legendas") else ""}
        else:
            if "{link_longo}" in item["descricao_youtube"] and not args.teste:
                print(f"{rotulo}: o vídeo longo ainda não tem link; envie o longo primeiro.")
                return 1
            dados, extras = meta(item, item["descricao_youtube"]), {}
        print(f"{rotulo}: {item['titulo']} → {dados.get('publishAt', 'agora (público)')}", flush=True)
        if args.teste:
            continue
        try:
            vid = enviar(raiz / item["arquivo"], dados, **extras)
        except RuntimeError as e:
            print(f"  falhou: {e}\n  Os itens restantes continuam pendentes; rode de novo depois.")
            return 1
        item["status"], item["url"] = "publicado" if item["hora"] == "agora" else "agendado", f"https://youtu.be/{vid}"
        if rotulo == "longo":
            for s in pac["shorts"]:
                s["descricao_youtube"] = s["descricao_youtube"].replace("{link_longo}", item["url"])
        salvar_json(caminho, pac)
        print(f"  agendado: {item['url']}")
    print("Falta à mão: 'Vídeo relacionado' de cada Short e o comentário fixado (a API não faz).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

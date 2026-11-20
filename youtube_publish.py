"""YouTube OAuth desktop flow and bounded resumable uploads."""
import base64
import ctypes
import hashlib
import json
import secrets
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ACCOUNT = ROOT / "work" / "youtube-account.dpapi"
TOKEN = "https://oauth2.googleapis.com/token"
AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
API = "https://www.googleapis.com/youtube/v3/"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"
SCOPE = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"
CHUNK = 4 * 1024**2


class UploadUncertain(RuntimeError):
    pass


class Blob(ctypes.Structure):
    _fields_ = [("length", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def protect(value, decrypt=False):
    if not hasattr(ctypes, "windll"):
        raise RuntimeError("A conexão OAuth usa o cofre do Windows.")
    carrier = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
    source, dest = Blob(len(value), carrier), Blob()
    operation = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(dest)):
        raise OSError("Não foi possível acessar a credencial do Windows.")
    try:
        return ctypes.string_at(dest.data, dest.length)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(dest.data, ctypes.c_void_p))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(url, *, data=None, headers=None, method=None, timeout=35):
    import truststore
    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context))
    return opener.open(req, timeout=timeout)


def read_json(url, token=None, params=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    data = urllib.parse.urlencode(params).encode() if params else None
    if data:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    with request(url, headers=headers, data=data) as response:
        return json.load(response)


def account():
    if not ACCOUNT.is_file():
        return None
    return json.loads(protect(ACCOUNT.read_bytes(), decrypt=True))


def exchange(client, **params):
    options = {"client_id": client["client_id"], **params}
    if client.get("client_secret"):
        options["client_secret"] = client["client_secret"]
    return read_json(TOKEN, params=options)


def identity(token):
    result = read_json(API + "channels?mine=true&part=snippet", token=token)
    channels = result.get("items", [])
    if len(channels) != 1:
        raise ValueError("Selecione uma conta que corresponda a um único canal do YouTube.")
    return {"id": channels[0]["id"], "title": channels[0]["snippet"]["title"]}


def connect(client_file):
    path = Path(client_file)
    if path.stat().st_size > 20_000:
        raise ValueError("Selecione o JSON OAuth de aplicativo para computador.")
    client = json.loads(path.read_text(encoding="utf-8-sig")).get("installed")
    if not isinstance(client, dict) or not str(client.get("client_id", "")).endswith(".apps.googleusercontent.com"):
        raise ValueError("Use um cliente OAuth do tipo aplicativo para computador.")
    client = {key: client[key] for key in ("client_id", "client_secret") if key in client}
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    returned = {}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            target = urllib.parse.urlsplit(self.path)
            values = urllib.parse.parse_qs(target.query)
            valid = target.path == "/" and secrets.compare_digest(values.get("state", [""])[0], state)
            if valid:
                returned.update((key, items[0]) for key, items in values.items() if items and key in ("code", "error"))
            self.send_response(200 if valid else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Volte ao Clip Studio para conferir o resultado.".encode("utf-8"))

    with HTTPServer(("127.0.0.1", 0), Callback) as server:
        server.timeout = 1
        redirect = f"http://127.0.0.1:{server.server_port}/"
        params = dict(client_id=client["client_id"], redirect_uri=redirect, scope=SCOPE, state=state,
                      response_type="code", code_challenge=challenge, code_challenge_method="S256",
                      access_type="offline", prompt="consent select_account")
        if not webbrowser.open(AUTH + "?" + urllib.parse.urlencode(params)):
            raise RuntimeError("Não foi possível abrir o navegador para autorizar.")
        end = time.monotonic() + 180
        while not returned and time.monotonic() < end:
            server.handle_request()
    if not returned.get("code"):
        raise RuntimeError("A autorização foi recusada ou expirou.")
    auth = exchange(client, grant_type="authorization_code", code=returned["code"],
                    code_verifier=verifier, redirect_uri=redirect)
    if not auth.get("refresh_token"):
        raise RuntimeError("A conta não entregou autorização para sessões futuras.")
    profile = identity(auth["access_token"])
    data = {"client": client, "refresh_token": auth["refresh_token"], "channel": profile}
    ACCOUNT.parent.mkdir(parents=True, exist_ok=True)
    draft = ACCOUNT.with_suffix(".tmp")
    draft.write_bytes(protect(json.dumps(data).encode()))
    draft.replace(ACCOUNT)
    return profile


def future_time(value):
    local = datetime.strptime(value, "%d/%m/%Y %H:%M").astimezone()
    if local.timestamp() < time.time() + 600:
        raise ValueError("Marque para pelo menos 10 minutos à frente.")
    return local.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def send(path, meta, publish_at, channel_id, progress=lambda _: None):
    saved = account()
    if not saved or saved["channel"]["id"] != channel_id:
        raise ValueError("Conecte o canal que você selecionou.")
    if datetime.fromisoformat(publish_at).timestamp() < time.time() + 300:
        raise ValueError("O horário está muito próximo. Selecione outra data.")
    token = exchange(saved["client"], grant_type="refresh_token", refresh_token=saved["refresh_token"])["access_token"]
    authorization = {"Authorization": f"Bearer {token}"}
    if identity(token)["id"] != channel_id:
        raise ValueError("A autorização não corresponde ao canal escolhido.")
    length = path.stat().st_size
    headers = {**authorization, "Content-Type": "application/json; charset=utf-8",
               "X-Upload-Content-Length": str(length), "X-Upload-Content-Type": "video/mp4"}
    item = {"snippet": {"title": meta["title"][:95], "description": meta["description"][:4900],
                         "categoryId": "20"},
            "status": {"privacyStatus": "private", "publishAt": publish_at,
                       "selfDeclaredMadeForKids": meta["kids"]}}
    with request(UPLOAD + "?part=snippet,status&uploadType=resumable", headers=headers,
                 data=json.dumps(item, ensure_ascii=False).encode("utf-8")) as response:
        location = response.headers.get("Location", "")
    endpoint = urllib.parse.urlsplit(location)
    if endpoint.scheme != "https" or endpoint.netloc not in {"www.googleapis.com", "youtube.googleapis.com"}:
        raise RuntimeError("O YouTube não retornou um endereço conhecido para o envio.")
    offset = 0
    with path.open("rb") as stream:
        while offset < length:
            data = stream.read(CHUNK)
            finish = offset + len(data)
            if not data:
                raise UploadUncertain("O arquivo mudou durante o envio.")
            if finish == length and datetime.fromisoformat(publish_at).timestamp() <= time.time() + 120:
                raise UploadUncertain("O horário se aproximou durante o envio. Confira o Studio antes de repetir.")
            headers = {**authorization, "Content-Type": "video/mp4",
                       "Content-Range": f"bytes {offset}-{finish-1}/{length}"}
            try:
                with request(location, headers=headers, data=data, method="PUT", timeout=120) as response:
                    result = json.load(response)
                    if "id" not in result:
                        raise UploadUncertain("Envio aceito sem ID. Confira o Studio antes de repetir.")
                    if meta.get("thumbnail"):
                        try:
                            set_thumbnail(token, result["id"], Path(meta["thumbnail"]))
                        except (OSError, ValueError, RuntimeError, KeyError):
                            result["thumbnail_warning"] = "A miniatura precisa ser aplicada pelo YouTube Studio."
                    return result
            except urllib.error.HTTPError as error:
                if error.code == 308 and error.headers.get("Range") == f"bytes=0-{finish-1}":
                    offset = finish
                    progress(f"Enviado {round(offset / length * 100)}%")
                    continue
                if 400 <= error.code < 500 and error.code != 408:
                    raise ValueError(f"YouTube recusou o envio (HTTP {error.code}).") from None
                raise UploadUncertain("Envio com resposta incompleta. Confira o Studio antes de repetir.") from None
            except (OSError, ValueError) as error:
                if isinstance(error, UploadUncertain):
                    raise
                raise UploadUncertain("Conexão interrompida durante o envio. Confira o Studio.") from error
    raise UploadUncertain("Envio encerrado sem confirmação do YouTube.")


def set_thumbnail(token, video_id, path):
    if not 0 < path.stat().st_size <= 2 * 1024 * 1024:
        raise ValueError("Use uma miniatura JPEG de até 2 MiB.")
    endpoint = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set?"
    endpoint += urllib.parse.urlencode({"videoId": video_id, "uploadType": "media"})
    with request(endpoint, data=path.read_bytes(),
                 headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"}) as response:
        return json.load(response)

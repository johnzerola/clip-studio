"""Discover working loopback Ollama services without changing the user's global setup."""
import json
import time
from urllib.request import ProxyHandler, build_opener

DEFAULT = "http://127.0.0.1:11434"
CACHE_SERVICE = "http://127.0.0.1:11435"
_probes = {}


def service_models(endpoint, *, refresh=False):
    now = time.monotonic()
    checked, models = _probes.get(endpoint, (0, None))
    if not refresh and now - checked < (15 if models is not None else 4):
        return models
    try:
        with build_opener(ProxyHandler({})).open(endpoint + "/api/tags", timeout=2.5) as reply:
            models = {item["name"] for item in json.load(reply)["models"]}
    except (OSError, KeyError, TypeError, ValueError):
        models = None
    _probes[endpoint] = (time.monotonic(), models)
    return models


def active_endpoint(model=None):
    for endpoint in (CACHE_SERVICE, DEFAULT):
        models = service_models(endpoint)
        if models is not None and (not model or model in models):
            return endpoint
    raise ConnectionError("Nenhum Ollama local saudável respondeu com o modelo solicitado.")


def forget_endpoint(endpoint):
    _probes.pop(endpoint, None)

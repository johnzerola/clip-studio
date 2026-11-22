"""Discover working loopback Ollama services without changing the user's global setup."""
import json
from urllib.request import ProxyHandler, build_opener

DEFAULT = "http://127.0.0.1:11434"
CACHE_SERVICE = "http://127.0.0.1:11435"


def service_models(endpoint):
    try:
        with build_opener(ProxyHandler({})).open(endpoint + "/api/tags", timeout=.8) as reply:
            return {item["name"] for item in json.load(reply)["models"]}
    except (OSError, KeyError, TypeError, ValueError):
        return None


def active_endpoint(model=None):
    healthy = None
    for endpoint in (DEFAULT, CACHE_SERVICE):
        models = service_models(endpoint)
        if models is not None:
            if not model or model in models:
                return endpoint
            healthy = healthy or endpoint
    return healthy or DEFAULT

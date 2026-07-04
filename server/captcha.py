import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

_API_KEY = os.getenv("TWOCAPTCHA_API_KEY")
_BASE = "https://2captcha.com"


def _resolver(params: dict, espera_inicial: int = 10, timeout: int = 180) -> str:
    r = requests.post(f"{_BASE}/in.php", data={**params, "key": _API_KEY, "json": 1}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != 1:
        raise RuntimeError(f"2captcha error al enviar: {data}")
    task_id = data["request"]
    time.sleep(espera_inicial)
    deadline = time.time() + timeout
    while time.time() < deadline:
        r2 = requests.get(f"{_BASE}/res.php", params={"key": _API_KEY, "action": "get", "id": task_id, "json": 1}, timeout=15)
        r2.raise_for_status()
        d2 = r2.json()
        if d2.get("status") == 1:
            return d2["request"]
        if d2.get("request") not in ("CAPCHA_NOT_READY", "CAPTCHA_NOT_READY"):
            raise RuntimeError(f"2captcha error al obtener: {d2}")
        time.sleep(5)
    raise TimeoutError("2captcha no respondió a tiempo")


def resolver_turnstile(sitekey: str, pageurl: str) -> str:
    return _resolver({"method": "turnstile", "sitekey": sitekey, "pageurl": pageurl}, espera_inicial=5, timeout=150)


def resolver_recaptcha_v2(sitekey: str, pageurl: str) -> str:
    return _resolver({"method": "userrecaptcha", "googlekey": sitekey, "pageurl": pageurl}, espera_inicial=15, timeout=180)


def saldo() -> float:
    r = requests.get(f"{_BASE}/res.php", params={"key": _API_KEY, "action": "getbalance"}, timeout=10)
    r.raise_for_status()
    return float(r.text)

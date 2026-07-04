import os
import requests
from dotenv import load_dotenv

load_dotenv()

_SERVER = os.getenv("SERVER_URL", "").rstrip("/")
_HEADERS = {"X-App-Secret": os.getenv("APP_SECRET", "")}


def resolver_turnstile(sitekey: str, pageurl: str) -> str:
    r = requests.post(
        f"{_SERVER}/captcha/turnstile",
        json={"sitekey": sitekey, "pageurl": pageurl},
        headers=_HEADERS,
        timeout=180,
    )
    r.raise_for_status()
    return r.json()["token"]


def resolver_recaptcha_v2(sitekey: str, pageurl: str) -> str:
    r = requests.post(
        f"{_SERVER}/captcha/recaptcha",
        json={"sitekey": sitekey, "pageurl": pageurl},
        headers=_HEADERS,
        timeout=210,
    )
    r.raise_for_status()
    return r.json()["token"]

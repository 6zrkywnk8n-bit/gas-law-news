"""HTTP 取得層。ブラウザ相当のヘッダ・リトライ・文字コード自動判定つき。"""
from __future__ import annotations

import gzip
import re
import ssl
import time
import urllib.error
import urllib.request
import zlib

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "close",
}

_META_CHARSET = re.compile(rb"""charset\s*=\s*["']?\s*([A-Za-z0-9_\-]+)""", re.I)
# 社内プロキシで証明書が差し替わっている環境でも止まらないようにする
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


class FetchError(Exception):
    pass


# 一部の官公庁サイト（経産省など）は Bot 対策の JavaScript チャレンジを返すことがある。
# 中身が本文でないことをここで見抜き、0 件を「取得成功」と誤認しないようにする。
_CHALLENGE_MARKERS = (
    "awsWafCookieDomainList",
    "gokuProps",
    "challenge-platform",
    "Just a moment...",
    "Checking your browser",
)


def looks_like_challenge(text: str) -> bool:
    if any(m in text for m in _CHALLENGE_MARKERS):
        return True
    # 本文が極端に短くリンクも無いページは、実質的な中身が無い
    return len(text) < 3000 and "<a " not in text and "<item" not in text


def _decompress(raw: bytes, encoding: str) -> bytes:
    enc = (encoding or "").lower()
    try:
        if "gzip" in enc:
            return gzip.decompress(raw)
        if "deflate" in enc:
            try:
                return zlib.decompress(raw)
            except zlib.error:
                return zlib.decompress(raw, -zlib.MAX_WBITS)
    except (OSError, zlib.error):
        return raw
    return raw


def _decode(raw: bytes, declared: str | None) -> str:
    """宣言された文字コードを優先しつつ、厳密デコードできたものを採用する。

    日本語サイトは meta の宣言が実体と食い違うことがあるため、
    「エラーなくデコードできるか」を最終的な判定基準にしている。
    """
    candidates: list[str] = []
    if declared:
        candidates.append(declared)
    m = _META_CHARSET.search(raw[:4096])
    if m:
        candidates.append(m.group(1).decode("ascii", "ignore"))
    candidates += ["utf-8", "cp932", "euc-jp"]

    seen: set[str] = set()
    for enc in candidates:
        key = enc.lower().replace("_", "-")
        if not key or key in seen:
            continue
        seen.add(key)
        try:
            return raw.decode(enc, "strict")
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace")


def fetch(url: str, timeout: int = 30, retries: int = 2, pause: float = 0.8) -> str:
    """URL の本文を文字列で返す。失敗時は FetchError。"""
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as resp:
                raw = _decompress(resp.read(), resp.headers.get("Content-Encoding", ""))
                declared = None
                ctype = resp.headers.get("Content-Type", "")
                cm = re.search(r"charset=([\w\-]+)", ctype, re.I)
                if cm:
                    declared = cm.group(1)
            time.sleep(pause)  # 相手サイトへの礼儀
            text = _decode(raw, declared)
            if looks_like_challenge(text):
                raise FetchError("アクセス制限（Bot対策）のため本文を取得できませんでした")
            return text
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            last = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise FetchError(f"{type(last).__name__}: {last}")

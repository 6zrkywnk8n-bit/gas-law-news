"""日付・文字列まわりの小道具（標準ライブラリのみ）。"""
from __future__ import annotations

import html
import re
import unicodedata
from datetime import date, datetime, timezone

# 元号 -> 西暦の開始年（改元年は「元年」を1年目として計算）
ERAS = {
    "令和": 2018,  # 令和元年 = 2019
    "平成": 1988,
    "昭和": 1925,
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\u3000]+")


def strip_tags(s: str) -> str:
    """タグを落として実体参照を戻し、空白を整える。"""
    s = _TAG_RE.sub(" ", s)
    s = html.unescape(s)
    s = _WS_RE.sub(" ", s).replace("\r", " ").replace("\n", " ")
    return s.strip()


def normalize(s: str) -> str:
    """全角英数字・記号を半角に寄せる（キーワード照合と日付解析用）。"""
    return unicodedata.normalize("NFKC", s)


def _era_to_year(era: str, num: str) -> int | None:
    base = ERAS.get(era)
    if base is None:
        return None
    n = 1 if num in ("元", "1") else None
    if n is None:
        try:
            n = int(num)
        except ValueError:
            return None
    return base + n


_DATE_PATTERNS = [
    # 2026-08-28 / 2026/8/28 / 2026.8.28
    (re.compile(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})"), "ymd"),
    # 2026年8月28日
    (re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"), "ymd"),
    # 令和8年8月27日 / 令和元年5月1日
    (re.compile(r"(令和|平成|昭和)\s*(元|\d{1,2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"), "era"),
    # 2026年8月（日が無い場合は1日扱い）
    (re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月"), "ym"),
]


def parse_date(text: str) -> date | None:
    """和暦・全角混じりの日本語テキストから最初の日付を取り出す。"""
    if not text:
        return None
    t = normalize(text)
    for pat, kind in _DATE_PATTERNS:
        m = pat.search(t)
        if not m:
            continue
        try:
            if kind == "era":
                y = _era_to_year(m.group(1), m.group(2))
                if y is None:
                    continue
                mo, d = int(m.group(3)), int(m.group(4))
            elif kind == "ym":
                y, mo, d = int(m.group(1)), int(m.group(2)), 1
            else:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return date(y, mo, d)
        except ValueError:
            continue
    return None


_RFC822 = "%a, %d %b %Y %H:%M:%S"


def parse_rss_date(text: str) -> date | None:
    """RSS の pubDate / Atom の updated を日付に。"""
    if not text:
        return None
    t = text.strip()
    # Atom: 2026-08-28T09:00:00Z
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    # RFC822: Thu, 28 Aug 2026 09:00:00 GMT
    m = re.match(r"[A-Za-z]{3}, \d{1,2} [A-Za-z]{3} \d{4} \d{2}:\d{2}:\d{2}", t)
    if m:
        try:
            return datetime.strptime(m.group(0), _RFC822).date()
        except ValueError:
            return None
    return parse_date(t)


_URL_DATE = [
    re.compile(r"[/_-](20\d{2})(\d{2})(\d{2})"),
    re.compile(r"/(20\d{2})/(\d{1,2})/(\d{1,2})[/_-]"),
    re.compile(r"/(20\d{2})/(\d{1,2})/"),
]


def date_from_url(url: str) -> date | None:
    """URL の年月ディレクトリ（/2026/08/ など）から日付を推定する。"""
    if not url:
        return None
    for pat in _URL_DATE:
        m = pat.search(url)
        if not m:
            continue
        g = m.groups()
        try:
            return date(int(g[0]), int(g[1]), int(g[2]) if len(g) > 2 else 1)
        except ValueError:
            continue
    return None


_PAREN_DATE = re.compile(r"[（(]([^（()）]*?\d[^（()）]*?日)[)）]")


def parse_date_prefer_paren(text: str) -> date | None:
    """末尾の「（令和８年８月27日）」を優先して日付を取る（消防庁の題名形式）。"""
    if not text:
        return None
    cands = _PAREN_DATE.findall(normalize(text))
    for chunk in reversed(cands):
        d = parse_date(chunk)
        if d:
            return d
    return parse_date(text)


_DEDUP_STRIP = re.compile(r"[\s　!-/:-@\[-`{-~。、「」『』（）・…ー~]+")


def dedup_key(title: str, published: str | None = None) -> str:
    """媒体違いの同一記事をまとめるための照合キー。

    Google ニュースは同じ発表を複数媒体ぶん返してくるため、
    記号と空白を落とした題名（＋日付）で名寄せする。
    """
    t = _DEDUP_STRIP.sub("", normalize(title).lower())
    # 配信元によって題名の末尾が切られるため、前方 32 文字だけで照合する
    return f"{t[:32]}|{published or ''}"


def today() -> date:
    return datetime.now(timezone.utc).astimezone().date()

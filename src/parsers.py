"""情報源ごとの一覧ページ／フィードを共通の項目形式に変換する。

返す項目: {"title", "url", "date"(date|None), "summary", "tag"}
"""
from __future__ import annotations

import re
from urllib.parse import urljoin
from xml.etree import ElementTree

from .util import date_from_url, parse_date, parse_date_prefer_paren, parse_rss_date, strip_tags

Item = dict


# ---------------------------------------------------------------- RSS / Atom
_ATOM = "{http://www.w3.org/2005/Atom}"


def parse_rss(text: str, base_url: str) -> list[Item]:
    try:
        root = ElementTree.fromstring(text.encode("utf-8"))
    except ElementTree.ParseError:
        return []

    items: list[Item] = []
    for node in root.iter():
        tag = node.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        get = lambda n: node.find(n) if node.find(n) is not None else node.find(_ATOM + n)

        title_el = get("title")
        title = strip_tags(title_el.text or "") if title_el is not None else ""

        link = ""
        link_el = node.find("link")
        if link_el is not None and (link_el.text or "").strip():
            link = link_el.text.strip()
        else:
            for cand in node.findall(_ATOM + "link"):
                if cand.get("rel") in (None, "alternate"):
                    link = cand.get("href", "")
                    break

        pub = ""
        for name in ("pubDate", "updated", "published", "date"):
            el = get(name)
            if el is not None and el.text:
                pub = el.text
                break

        desc = ""
        for name in ("description", "summary", "content"):
            el = get(name)
            if el is not None and el.text:
                desc = strip_tags(el.text)
                break

        # Google ニュースは「タイトル - 媒体名」形式。媒体名を出典タグに回す。
        tag_name = ""
        src_el = node.find("source")
        if src_el is not None and (src_el.text or "").strip():
            tag_name = src_el.text.strip()
            if title.endswith(" - " + tag_name):
                title = title[: -(len(tag_name) + 3)].strip()

        if title and link:
            items.append({
                "title": title,
                "url": urljoin(base_url, link),
                "date": parse_rss_date(pub),
                "summary": desc[:300],
                "tag": tag_name,
            })
    return items


# ---------------------------------------------------- 経済産業省 ニュースリリース
_METI_RE = re.compile(
    r'<div class="left txt_box">\s*<p>(?P<date>[^<]+)</p>\s*'
    r'<a[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.S,
)


def parse_meti_press(text: str, base_url: str) -> list[Item]:
    items: list[Item] = []
    for m in _METI_RE.finditer(text):
        title = strip_tags(m.group("title"))
        if not title:
            continue
        items.append({
            "title": title,
            "url": urljoin(base_url, m.group("url")),
            "date": parse_date(m.group("date")),
            "summary": "",
            "tag": "ニュースリリース",
        })
    return items


# ------------------------------------------------------------ 消防庁 報道発表等
# ページは h2 見出しごとにブロックが分かれている。見出し名をそのままタグに使う。
_FDMA_BLOCK = re.compile(
    r'<div class="row"[^>]*id="anchor--\d+"[^>]*>(?P<block>.*?)(?=<div class="row"|<footer)',
    re.S,
)
_FDMA_H2 = re.compile(r"<h2[^>]*>(?P<h>.*?)</h2>", re.S)
_FDMA_ITEM = re.compile(r'<li>\s*<a[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>', re.S)
_WANTED_HEADINGS = ("報道発表", "お知らせ", "パブリック・コメント", "消費者事故")


def parse_fdma_press(text: str, base_url: str) -> list[Item]:
    items: list[Item] = []
    for blk in _FDMA_BLOCK.finditer(text):
        block = blk.group("block")
        hm = _FDMA_H2.search(block)
        heading = strip_tags(hm.group("h")) if hm else ""
        if heading and not any(w in heading for w in _WANTED_HEADINGS):
            continue
        for m in _FDMA_ITEM.finditer(block):
            title = strip_tags(m.group("title"))
            if not title:
                continue
            items.append({
                "title": title,
                "url": urljoin(base_url, m.group("url")),
                "date": parse_date_prefer_paren(title),  # 日付は「（令和８年８月27日）」として題名末尾にある
                "summary": "",
                "tag": heading,
            })
    return items


# --------------------------------------------------- 高圧ガス保安協会 (KHK) 新着
_KHK_ITEM = re.compile(
    r'<p class="dateIcon"><time>(?P<date>[^<]+)</time>'
    r'(?:\s*<span class="categoryIcon"[^>]*?name="(?P<cat>[^"]*)")?.*?'
    r'<p class="description">\s*<a[^>]*href=(?P<q>["\'])(?P<url>.*?)(?P=q)[^>]*>(?P<title>.*?)</a>',
    re.S,
)


def parse_khk_news(text: str, base_url: str) -> list[Item]:
    items: list[Item] = []
    for m in _KHK_ITEM.finditer(text):
        title = strip_tags(m.group("title"))
        if not title:
            continue
        items.append({
            "title": title,
            "url": urljoin(base_url, m.group("url")),
            "date": parse_date(m.group("date")),
            "summary": "",
            "tag": (m.group("cat") or "").strip(),
        })
    return items


# ------------------------------------------------------------ 汎用リストパーサ
# 「リンク」と「その近くにある日付」を拾う。構造が読めないサイト向けの保険。
_ANCHOR = re.compile(r'<a[^>]*href=(["\'])(?P<url>.*?)\1[^>]*>(?P<title>.*?)</a>', re.S)


def parse_generic_list(text: str, base_url: str) -> list[Item]:
    items: list[Item] = []
    seen: set[str] = set()
    for m in _ANCHOR.finditer(text):
        title = strip_tags(m.group("title"))
        url = m.group("url").strip()
        if len(title) < 8 or url.startswith(("#", "javascript:", "mailto:")):
            continue
        full = urljoin(base_url, url)
        if full in seen:
            continue
        seen.add(full)
        # 直前 300 文字（日付が前置されるレイアウトが多い）→ なければ題名から
        near = text[max(0, m.start() - 300):m.start()]
        items.append({
            "title": title,
            "url": full,
            "date": parse_date(strip_tags(near)) or parse_date(title) or date_from_url(full),
            "summary": "",
            "tag": "",
        })
    return items


def parse(kind: str, text: str, base_url: str) -> list[Item]:
    """パーサを名前で呼び出し、日付が取れなかった項目は URL から補完する。"""
    items = PARSERS[kind](text, base_url)
    for it in items:
        if not it.get("date"):
            it["date"] = date_from_url(it["url"])
    return items


PARSERS = {
    "rss": parse_rss,
    "meti_press": parse_meti_press,
    "fdma_press": parse_fdma_press,
    "khk_news": parse_khk_news,
    "generic_list": parse_generic_list,
}

"""保安法令ニュース収集ツール

高圧ガス保安法・液化石油ガス法・火薬類取締法に関する情報を
官公庁／業界団体／ニュース検索から集め、HTML ダッシュボードにまとめる。

使い方:
    python main.py              収集して dist/index.html を更新し、ブラウザで開く
    python main.py --no-open    ブラウザを開かない（定時実行向け）
    python main.py --no-fetch   収集せず、蓄積済みデータから作り直すだけ
    python main.py --only khk_top,meti_press   特定の情報源だけ収集
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from datetime import date, timedelta
from pathlib import Path

from src.classify import SIGNAL_WEIGHTS, Classifier
from src.fetcher import FetchError, fetch
from src.parsers import parse
from src.render import render_dashboard
from src.store import Store, make_id
from src.util import dedup_key
from src.util import today as today_local

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"
DB_PATH = ROOT / "data" / "news.db"
OUT_PATH = ROOT / "dist" / "index.html"

# 収集対象とする発行日の下限。これより古い記事は保存しない。
MAX_AGE_DAYS = 400


def log(msg: str) -> None:
    """cp932 のコンソールでも落ちないように出力する。"""
    enc = sys.stdout.encoding or "utf-8"
    sys.stdout.write(msg.encode(enc, "replace").decode(enc) + "\n")
    sys.stdout.flush()


def collect(sources: list[dict], clf: Classifier, store: Store, cutoff: date) -> list[dict]:
    """各情報源を巡回して DB に取り込み、情報源ごとの結果を返す。"""
    stats: list[dict] = []
    seen_urls: set[str] = set()

    for src in sources:
        stat = {
            "id": src["id"], "name": src["name"], "category": src["category"],
            "fetched": 0, "kept": 0, "added": 0, "error": "",
        }
        try:
            text = fetch(src["url"])
            items = parse(src["parser"], text, src["url"])
        except FetchError as exc:
            stat["error"] = f"取得失敗: {exc}"[:120]
            stats.append(stat)
            log(f"  [NG] {src['name']}: {stat['error']}")
            continue
        except Exception as exc:  # パーサ側の想定外はそのソースだけ諦める
            stat["error"] = f"解析失敗: {type(exc).__name__}"
            stats.append(stat)
            log(f"  [NG] {src['name']}: {stat['error']}")
            continue

        stat["fetched"] = len(items)
        for it in items:
            if it["url"] in seen_urls:  # 別ソースで既に採用済み
                continue
            if it["date"] and it["date"] < cutoff:
                continue

            verdict = clf.classify(it["title"], it.get("summary", ""))
            if src.get("filter", False) and not verdict["relevant"]:
                continue
            if not verdict["laws"]:
                # 所管が自明な情報源（協会サイトなど）は既定の法令を当てる
                verdict["laws"] = list(src.get("default_laws", []))

            seen_urls.add(it["url"])
            stat["kept"] += 1
            published = it["date"].isoformat() if it["date"] else None
            rec = {
                "id": make_id(it["url"], it["title"]),
                "source_id": src["id"], "source_name": src["name"], "category": src["category"],
                "title": it["title"], "url": it["url"],
                "published": published,
                "summary": it.get("summary", ""), "tag": it.get("tag", ""),
                "laws": verdict["laws"], "signals": verdict["signals"],
                "keywords": verdict["keywords"], "score": verdict["score"],
                "dupkey": dedup_key(it["title"], published),
            }
            if store.upsert(rec):
                stat["added"] += 1

        store.commit()
        stats.append(stat)
        log(f"  [OK] {src['name']}: 取得{stat['fetched']} / 採用{stat['kept']} / 新規{stat['added']}")

    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="保安法令ニュース収集ツール")
    ap.add_argument("--no-fetch", action="store_true", help="収集せず蓄積済みデータから作り直す")
    ap.add_argument("--no-open", action="store_true", help="生成後にブラウザを開かない")
    ap.add_argument("--only", default="", help="収集する情報源 ID をカンマ区切りで指定")
    args = ap.parse_args()

    sources_cfg = json.loads((CONFIG / "sources.json").read_text(encoding="utf-8"))
    sources = [s for s in sources_cfg["sources"] if s.get("enabled", True)]
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        sources = [s for s in sources if s["id"] in wanted]

    clf = Classifier(CONFIG / "keywords.json")
    store = Store(DB_PATH)
    prev_run = store.previous_run_at()

    stats: list[dict] = []
    if args.no_fetch:
        log("収集をスキップし、蓄積済みデータから再生成します。")
        stats = [{"id": s["id"], "name": s["name"], "category": s["category"],
                  "fetched": 0, "kept": 0, "added": 0,
                  "error": "今回はスキップ", "skipped": True} for s in sources]
    else:
        log(f"{len(sources)} 件の情報源を巡回します...")
        cutoff = today_local() - timedelta(days=MAX_AGE_DAYS)
        stats = collect(sources, clf, store, cutoff)

    items = store.all_items()
    # 前回実行より後に初めて見つかったものを「新着」として印を付ける
    for it in items:
        it["is_new"] = bool(prev_run) and it["first_seen"] > prev_run

    # GitHub Actions 上で動いているときは、手動実行ページへのリンクを埋め込む
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    actions_url = f"https://github.com/{repo}/actions/workflows/update.yml" if repo else ""

    out = render_dashboard(
        OUT_PATH, items, stats, clf.meta, list(SIGNAL_WEIGHTS.keys()),
        prev_run, today_local().isoformat(), actions_url,
    )
    if not args.no_fetch:
        store.record_run({"sources": len(stats), "added": sum(s["added"] for s in stats)})
    store.close()

    new_count = sum(1 for it in items if it["is_new"])
    log(f"\n完了: 収録 {len(items)} 件（うち新着 {new_count} 件）")
    log(f"ダッシュボード: {out}")
    if not args.no_open:
        webbrowser.open(out.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

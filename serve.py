"""同じ Wi-Fi のスマホからダッシュボードを見るための簡易サーバー。

dist/ を LAN に公開し、ページ内の「最新に更新」ボタンから収集を実行できるようにする。
表示された URL をスマホのブラウザで開くだけ。Ctrl+C か、このウィンドウを閉じると停止する。

    python serve.py            8765 番ポートで起動
    python serve.py --port 80  ポートを変える
    python serve.py --no-update 起動時の収集をしない

公開する API は 2 つだけで、どちらもリクエストの中身を一切使わない。
  GET  /api/ping    収集サーバーかどうかをページ側が確かめるためのもの
  POST /api/update  main.py を決め打ちで実行する（引数は受け取らない）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
DEFAULT_PORT = 8765
UPDATE_TIMEOUT = 280  # 秒。ページ側の待ち時間より短くしておく

# 収集は同時に 1 本だけ。スマホと PC から同時に押されても二重実行しない。
_update_lock = threading.Lock()


def lan_ip() -> str:
    """このPCが LAN 内で名乗っている IP アドレスを調べる。

    外部に接続はせず、OS にどの経路を使うかだけ聞いている。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 1))  # ドキュメント用アドレス。実際の通信は発生しない
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def run_collector() -> dict:
    """main.py を実行し、その結果を要約して返す。"""
    if not _update_lock.acquire(blocking=False):
        return {"ok": False, "error": "別の更新が進行中です。終わるまでお待ちください。"}
    try:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "main.py"), "--no-open"],
            cwd=ROOT, capture_output=True, timeout=UPDATE_TIMEOUT,
            # パイプ越しだと既定が cp932 になり件数の読み取りに失敗するので固定する
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "収集が時間内に終わりませんでした。"}
    except OSError as exc:
        return {"ok": False, "error": f"収集を起動できませんでした: {exc}"}
    finally:
        _update_lock.release()

    out = proc.stdout.decode("utf-8", "replace")
    if proc.returncode != 0:
        tail = (proc.stderr.decode("utf-8", "replace") or out).strip().splitlines()
        return {"ok": False, "error": (tail[-1] if tail else "収集に失敗しました")[:200]}

    # 「完了: 収録 161 件（うち新着 3 件）」から件数を拾う
    m = re.search(r"収録\s*(\d+)\s*件（うち新着\s*(\d+)\s*件）", out)
    total, added = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    print(f"  更新しました: 収録 {total} 件 / 新着 {added} 件")
    return {"ok": True, "total": total, "added": added}


class Handler(SimpleHTTPRequestHandler):
    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.split("?")[0].rstrip("/") == "/api/ping":
            self._send_json({"ok": True})
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path.split("?")[0].rstrip("/") == "/api/update":
            print("  スマホ/ブラウザから更新を要求されました。収集します...")
            self._send_json(run_collector())
            return
        self._send_json({"ok": False, "error": "not found"}, 404)

    def end_headers(self) -> None:
        # 更新後にスマホ側で古い内容が残らないようにする
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:
        pass  # アクセスログは出さない


def main() -> int:
    ap = argparse.ArgumentParser(description="ダッシュボードを同一 Wi-Fi 内に公開する")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-update", action="store_true", help="起動時に収集しない")
    args = ap.parse_args()

    if not args.no_update:
        print("起動前に収集しています...")
        subprocess.run([sys.executable, str(ROOT / "main.py"), "--no-open"], cwd=ROOT, check=False)

    if not (DIST / "index.html").exists():
        print("dist/index.html がありません。先に update.bat を実行してください。")
        return 1

    ip = lan_ip()
    try:
        httpd = ThreadingHTTPServer(("0.0.0.0", args.port), partial(Handler, directory=str(DIST)))
    except OSError as exc:
        print(f"ポート {args.port} を使えませんでした: {exc}")
        print(f"別のポートで試してください:  python serve.py --port {args.port + 1}")
        return 1

    bar = "=" * 56
    print(f"\n{bar}\n  スマホのブラウザで次の URL を開いてください\n")
    print(f"      http://{ip}:{args.port}/\n")
    print("  ・PC とスマホが同じ Wi-Fi につながっている必要があります")
    print("  ・初回は Windows ファイアウォールの確認が出ます。")
    print("    「プライベート ネットワーク」を許可してください")
    print("  ・ページ上の「最新に更新」ボタンでスマホから収集を実行できます")
    print("  ・止めるときは Ctrl+C、またはこのウィンドウを閉じます")
    print(f"  ・このPC からは http://localhost:{args.port}/\n{bar}\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n停止しました。")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

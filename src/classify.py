"""記事を三法令に振り分け、実務的な重要度を点数化する。"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .util import normalize

# 「改正されたのか / 事故が起きたのか / 単なる講習案内か」を見分けるための語。
# 業務で先に読むべきものを上に押し上げるのが狙い。
SIGNAL_WEIGHTS = {
    "法令改正": (18, ["改正", "施行", "省令", "政令", "告示", "公布", "新設", "廃止", "経過措置"]),
    "意見公募": (16, ["パブリックコメント", "パブリック・コメント", "意見公募", "意見募集", "答申", "審議会", "小委員会", "検討会"]),
    "事故": (14, ["事故", "爆発", "火災", "漏えい", "漏洩", "死亡", "負傷", "災害", "調査委員会", "原因調査"]),
    "行政処分": (12, ["行政処分", "立入検査", "命令", "指導", "回収", "リコール", "違反", "注意喚起", "緊急点検"]),
    "通達・解釈": (10, ["通達", "解釈", "運用", "基準", "ガイドライン", "手引き", "例示基準", "技術基準", "様式"]),
    "講習・試験": (3, ["講習", "検定", "国家試験", "受験", "申請受付", "テキスト", "資格"]),
}


class Classifier:
    def __init__(self, keywords_path: Path):
        cfg = json.loads(keywords_path.read_text(encoding="utf-8"))
        self.laws = cfg["laws"]
        self.exclude = cfg.get("exclude", [])
        self.meta = {
            name: {"color": spec.get("color", "#666"), "short": spec.get("short", name)}
            for name, spec in self.laws.items()
        }

    def classify(self, title: str, summary: str = "") -> dict:
        """該当法令・重要度・当たったキーワードを返す。"""
        text = normalize(f"{title} {summary}")

        matched_laws: list[str] = []
        hits: list[str] = []
        law_score = 0
        for law, spec in self.laws.items():
            s, kws = 0, []
            for kw in spec.get("strong", []):
                if normalize(kw) in text:
                    s += 10
                    kws.append(kw)
            for kw in spec.get("normal", []):
                if normalize(kw) in text:
                    s += 4
                    kws.append(kw)
            if s:
                matched_laws.append(law)
                hits.extend(kws)
                law_score += s

        signals: list[str] = []
        signal_score = 0
        for label, (weight, words) in SIGNAL_WEIGHTS.items():
            if any(normalize(w) in text for w in words):
                signals.append(label)
                signal_score += weight

        noise = any(normalize(w) in text for w in self.exclude)
        score = 0 if noise else min(100, law_score + signal_score)

        return {
            "laws": matched_laws,
            "signals": signals,
            "keywords": sorted(set(hits))[:8],
            "score": score,
            "relevant": bool(matched_laws) and not noise,
        }

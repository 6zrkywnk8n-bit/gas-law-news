"""収集結果から HTML ダッシュボードを書き出す。

2 種類を同時に出力する。
  dist/index.html    ローカルで開く／LAN 配信する単体ファイル
  dist/artifact.html Artifact 公開用（<html><head><body> を持たない本文のみ）

デザインの方針:
  配色 — 計器や鋼材を思わせる寒色寄りのニュートラル。選択状態は「地と文字の反転」で
         表し、色相は法令の分類だけに使う。青い選択色と青い法令バッジが紛れないようにする。
  書体 — 本文は端末標準の日本語ゴシック（読み込み不要で iOS/Android どちらでも正しい）。
         日付・数値だけ IBM Plex Mono に寄せて、計器の目盛りのような可読性を持たせる。
  構成 — 上から要約タイル、絞り込み、一覧。一覧は各行の左端に法令色の帯を引き、
         本文を読まなくても左端を目で追うだけで拾えるようにする。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

TITLE = "<title>保安法令ニュース</title>"

# 単体ファイル用の <head> 要素。Artifact 側は head を自前で持てないため分けてある。
HEAD_EXTRA = """<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#f3f5f7" media="(prefers-color-scheme:light)">
<meta name="theme-color" content="#0f1317" media="(prefers-color-scheme:dark)">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="保安法令ニュース">"""

BODY = r"""<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600&display=swap">
<style>
:root{
  --bg:#f3f5f7; --panel:#ffffff; --ink:#151a1f; --muted:#5a6673; --line:#dee4ea;
  --chip:#eaeef3; --field:#f7f9fb;
  --sel-bg:#151a1f; --sel-ink:#ffffff;
  --new:#8a5a09; --new-bg:#fdf1d6;
  --mark:#fde68a; --mark-ink:#3a2f12;
  --alert:#b4462f;
  --shadow:0 1px 2px rgba(21,26,31,.05), 0 1px 3px rgba(21,26,31,.04);
  --mono:"IBM Plex Mono", ui-monospace, "Cascadia Mono", Consolas, "Courier New", monospace;
  --jp:system-ui, -apple-system, "Segoe UI", "Yu Gothic UI", "Hiragino Kaku Gothic ProN",
      "Noto Sans JP", Meiryo, sans-serif;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --bg:#0f1317; --panel:#161b21; --ink:#e3e8ed; --muted:#93a0ad; --line:#242b33;
    --chip:#1e242b; --field:#12171c;
    --sel-bg:#e3e8ed; --sel-ink:#0f1317;
    --new:#f0c264; --new-bg:#33280e;
    --mark:#6d5010; --mark-ink:#f5efdf;
    --alert:#e07a62;
    --shadow:none;
  }
}
:root[data-theme="dark"]{
  --bg:#0f1317; --panel:#161b21; --ink:#e3e8ed; --muted:#93a0ad; --line:#242b33;
  --chip:#1e242b; --field:#12171c;
  --sel-bg:#e3e8ed; --sel-ink:#0f1317;
  --new:#f0c264; --new-bg:#33280e;
  --mark:#6d5010; --mark-ink:#f5efdf;
  --alert:#e07a62;
  --shadow:none;
}

*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--jp);
  font-size:14px;line-height:1.65;-webkit-font-smoothing:antialiased;
  -webkit-text-size-adjust:100%}
a{color:inherit}
:focus-visible{outline:2px solid var(--ink);outline-offset:2px;border-radius:4px}
.wrap{max-width:1180px;margin:0 auto;padding:22px 18px 64px}

header.top{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 16px;margin-bottom:18px}
header.top h1{font-size:19px;margin:0;letter-spacing:.01em;text-wrap:balance}
header.top .meta{color:var(--muted);font-size:11.5px;font-family:var(--mono);font-weight:500}

.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:10px;margin-bottom:18px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:11px 13px;
  box-shadow:var(--shadow)}
.kpi b{display:block;font-size:24px;line-height:1.2;font-family:var(--mono);font-weight:600;
  letter-spacing:-.01em}
.kpi span{color:var(--muted);font-size:11.5px}
.kpi.flag b{color:var(--alert)}

.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;box-shadow:var(--shadow)}
.filters{padding:12px 14px;margin-bottom:14px;display:flex;flex-direction:column;gap:10px}
.frow{display:flex;flex-wrap:wrap;gap:7px;align-items:center}
.frow>label.lb{color:var(--muted);font-size:11px;letter-spacing:.06em;min-width:52px}
.chip{border:1px solid var(--line);background:var(--chip);color:var(--ink);border-radius:999px;
  padding:4px 11px;font:inherit;font-size:12.5px;cursor:pointer;user-select:none;
  transition:background .12s,border-color .12s,color .12s}
.chip:hover{border-color:var(--muted)}
.chip[aria-pressed="true"]{background:var(--sel-bg);border-color:var(--sel-bg);color:var(--sel-ink)}
.chip .n{opacity:.6;margin-left:5px;font-size:11px;font-family:var(--mono);font-weight:500}
input[type=search],select{background:var(--field);color:var(--ink);border:1px solid var(--line);
  border-radius:8px;padding:6px 10px;font:inherit;font-size:13px}
input[type=search]{flex:1;min-width:200px}
.btn{border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:8px;
  padding:6px 12px;font:inherit;font-size:12.5px;cursor:pointer}
.btn:hover{border-color:var(--muted)}
.btn:disabled{opacity:.55;cursor:default}

.toprow{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
.btn.primary{background:var(--sel-bg);color:var(--sel-ink);border-color:var(--sel-bg);font-weight:600}
.btn.primary:hover:not(:disabled){opacity:.86}
.updstat{color:var(--muted);font-size:11.5px}
.updstat.bad{color:var(--alert)}

.count{color:var(--muted);font-size:11.5px;font-family:var(--mono);font-weight:500;margin:0 2px 8px}
ul.list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}
li.item{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--c,var(--line));
  border-radius:10px;padding:11px 13px;box-shadow:var(--shadow);
  display:grid;grid-template-columns:1fr auto;gap:4px 12px}
li.item.read{opacity:.48}
li.item .line1{grid-column:1/2;display:flex;flex-wrap:wrap;gap:6px;align-items:center;
  font-size:11.5px;color:var(--muted)}
li.item .date{font-family:var(--mono);font-weight:600;font-size:11.5px;color:var(--ink)}
li.item .title{grid-column:1/2;font-size:14.5px;font-weight:600;line-height:1.5;
  text-decoration:none;overflow-wrap:anywhere}
li.item .title:hover{text-decoration:underline;text-underline-offset:3px}
li.item .line3{grid-column:1/2;font-size:11.5px;color:var(--muted);overflow-wrap:anywhere}
li.item .acts{grid-column:2/3;grid-row:1/4;display:flex;flex-direction:column;gap:4px;align-items:flex-end}
.iconbtn{border:1px solid var(--line);background:transparent;border-radius:7px;width:30px;height:26px;
  cursor:pointer;font-size:13px;line-height:1;color:var(--muted);padding:0}
.iconbtn:hover{border-color:var(--muted);color:var(--ink)}
.iconbtn.on{color:#c98a12;border-color:#c98a12}

.badge{display:inline-block;border-radius:5px;padding:1px 7px;font-size:11px;font-weight:600;
  white-space:nowrap;border:1px solid transparent}
/* 法令は塗りつぶさず、色相を淡く敷いて文字色に寄せる。
   ink と混ぜているので、明暗どちらのテーマでも自動的に読める側へ振れる。 */
.badge.law{color:var(--c);background:transparent;border-color:var(--line)}
.badge.law{color:color-mix(in oklab, var(--c) 74%, var(--ink));
  background:color-mix(in oklab, var(--c) 13%, transparent);
  border-color:color-mix(in oklab, var(--c) 30%, transparent)}
.badge.sig{background:var(--chip);color:var(--muted);border-color:var(--line);font-weight:500}
.badge.newmark{background:var(--new-bg);color:var(--new);font-weight:700;letter-spacing:.04em}
mark{background:var(--mark);color:var(--mark-ink);border-radius:3px;padding:0 1px}

details.sources{margin-top:26px}
details.sources summary{cursor:pointer;color:var(--muted);font-size:12.5px;padding:4px 0}
.srcscroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table.src{width:100%;border-collapse:collapse;font-size:12px;margin-top:8px}
table.src th,table.src td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;
  white-space:nowrap}
table.src th{color:var(--muted);font-weight:600}
table.src td.num{text-align:right;font-family:var(--mono);font-weight:500}
.err{color:var(--alert)}
.empty{padding:34px;text-align:center;color:var(--muted)}
footer.note{margin-top:26px;color:var(--muted);font-size:11.5px;line-height:1.85}
footer.note code{background:var(--chip);padding:1px 6px;border-radius:5px;font-family:var(--mono);
  font-size:11px}
.fold{display:none}
@media (prefers-reduced-motion:reduce){*{transition:none !important;animation:none !important}}

/* --- スマートフォン --- */
@media(max-width:700px){
  .wrap{padding:14px max(12px,env(safe-area-inset-left)) 56px}
  header.top{gap:2px 12px;margin-bottom:12px}
  header.top h1{font-size:17px;width:100%}
  .kpis{grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:12px}
  .kpi{padding:9px 11px}
  .kpi b{font-size:21px}
  /* 絞り込みは既定で畳む。狭い画面はニュース本体に使う */
  .fold{display:block;width:100%;text-align:left;margin-bottom:10px;padding:10px 13px;font-size:13.5px}
  .filters.collapsed{display:none}
  .frow>label.lb{min-width:100%;margin-bottom:-2px}
  input[type=search]{min-width:100%}
  select{flex:1;min-width:0}
  /* 16px 未満だと iOS Safari が入力時に自動ズームしてしまう */
  input[type=search],select{padding:9px 10px;font-size:16px}
  .chip{padding:7px 13px;font-size:13px}
  .btn{padding:9px 13px;font-size:13px}
  li.item{grid-template-columns:1fr;padding:12px 12px 12px 11px}
  li.item .title{font-size:15px}
  li.item .acts{grid-column:1/2;grid-row:auto;flex-direction:row;justify-content:flex-end;
    gap:8px;margin-top:4px}
  .iconbtn{width:46px;height:38px;font-size:16px}
  table.src{min-width:560px}
}
</style>

<div class="wrap">
<header class="top">
  <h1>保安法令ニュース</h1>
  <div class="meta">更新 __GENERATED__ ／ 収録 __TOTAL__ 件 ／ 前回 __PREV__</div>
</header>

<div class="kpis" id="kpis"></div>

<div class="toprow">
  <button class="btn fold" id="toggleFilters" aria-expanded="false">絞り込み <span id="fcount"></span></button>
  <button class="btn primary" id="btnUpdate" hidden>最新に更新</button>
__MANUAL__
  <span class="updstat" id="updStatus" role="status" aria-live="polite"></span>
</div>
<div class="panel filters" id="filters">
  <div class="frow">
    <label class="lb">法令</label>
    <span id="lawChips"></span>
  </div>
  <div class="frow">
    <label class="lb">内容</label>
    <span id="sigChips"></span>
  </div>
  <div class="frow">
    <label class="lb">絞り込み</label>
    <input type="search" id="q" placeholder="キーワード検索（タイトル・出典・要約）">
    <select id="cat" aria-label="出典で絞り込む"><option value="">出典すべて</option></select>
    <select id="days" aria-label="期間で絞り込む">
      <option value="30">直近30日</option>
      <option value="90" selected>直近90日</option>
      <option value="180">直近180日</option>
      <option value="365">直近1年</option>
      <option value="0">すべて</option>
    </select>
    <select id="sort" aria-label="並び順">
      <option value="date">新しい順</option>
      <option value="score">重要度順</option>
    </select>
  </div>
  <div class="frow">
    <label class="lb"></label>
    <button class="chip" id="fNew" aria-pressed="false">新着のみ</button>
    <button class="chip" id="fStar" aria-pressed="false">★のみ</button>
    <button class="chip" id="fUnread" aria-pressed="false">未読のみ</button>
    <button class="btn" id="copyMd">一覧をコピー</button>
    <button class="btn" id="dlCsv">CSVで保存</button>
    <button class="btn" id="reset">条件クリア</button>
  </div>
</div>

<div class="count" id="count"></div>
<ul class="list" id="list"></ul>

<details class="sources">
  <summary>情報源の取得状況（__OKCOUNT__/__SRCCOUNT__ 成功）</summary>
  <div class="srcscroll">
    <table class="src">
      <thead><tr><th>情報源</th><th>区分</th><th class="num">取得</th><th class="num">採用</th><th class="num">新規</th><th>状態</th></tr></thead>
      <tbody id="srcbody"></tbody>
    </table>
  </div>
</details>

<footer class="note">
  __FOOTNOTE__<br>
  情報源の追加・停止は <code>config\sources.json</code>、法令の判定キーワードは <code>config\keywords.json</code> で調整できます。<br>
  ★と既読はこのブラウザにのみ保存されます。掲載しているのは各配信元の見出しへのリンクです。法令の条文・解釈は必ず原典（e-Gov法令検索・所管官庁の告示）でご確認ください。
</footer>
</div>

<script>
const DATA = __DATA__;
const SOURCES = __SOURCES__;
const LAWMETA = __LAWMETA__;
const SIGNALS = __SIGNALS__;
const TODAY = "__TODAY__";
// Artifact ビューアはページ発のファイル保存を許可しないため、CSV ボタンを出さない
const IS_ARTIFACT = __ARTIFACT__;

const LS = "gasnews.v1";
let state = {star:{}, read:{}};
try { state = Object.assign(state, JSON.parse(localStorage.getItem(LS) || "{}")); } catch(e) {}
const save = () => { try { localStorage.setItem(LS, JSON.stringify(state)); } catch(e) {} };

const F = {laws:new Set(), sigs:new Set(), q:"", cat:"", days:90, sort:"date", onlyNew:false, onlyStar:false, onlyUnread:false};
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const daysAgo = d => d ? Math.floor((new Date(TODAY) - new Date(d)) / 86400000) : 99999;
const lawColor = it => (it.laws.length && LAWMETA[it.laws[0]]) ? LAWMETA[it.laws[0]].color : "";

function highlight(text, q){
  const e = esc(text);
  if(!q) return e;
  const terms = q.split(/\s+/).filter(t => t.length > 0).map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  if(!terms.length) return e;
  return e.replace(new RegExp("(" + terms.join("|") + ")", "gi"), "<mark>$1</mark>");
}

function matches(it){
  if(F.laws.size && !it.laws.some(l => F.laws.has(l))) return false;
  if(F.sigs.size && !it.signals.some(s => F.sigs.has(s))) return false;
  if(F.cat && it.category !== F.cat) return false;
  if(F.days && daysAgo(it.published) > F.days) return false;
  if(F.onlyNew && !it.is_new) return false;
  if(F.onlyStar && !state.star[it.id]) return false;
  if(F.onlyUnread && state.read[it.id]) return false;
  if(F.q){
    const hay = (it.title + " " + it.source_name + " " + it.summary + " " + it.tag + " " + it.keywords.join(" ")).toLowerCase();
    if(!F.q.toLowerCase().split(/\s+/).filter(Boolean).every(t => hay.includes(t))) return false;
  }
  return true;
}

function visible(){
  const out = DATA.filter(matches);
  out.sort(F.sort === "score"
    ? (a,b) => (b.score - a.score) || ((b.published||"") > (a.published||"") ? 1 : -1)
    : (a,b) => ((b.published||"") > (a.published||"") ? 1 : (b.published === a.published ? b.score - a.score : -1)));
  return out;
}

function chipHtml(label, n){
  return '<button class="chip" data-v="' + esc(label) + '" aria-pressed="false">' + esc(label) + '<span class="n">' + n + '</span></button>';
}

function buildChips(){
  const lawCounts = {}, sigCounts = {};
  DATA.forEach(it => { it.laws.forEach(l => lawCounts[l] = (lawCounts[l]||0)+1);
                       it.signals.forEach(s => sigCounts[s] = (sigCounts[s]||0)+1); });
  $("#lawChips").innerHTML = Object.keys(LAWMETA).map(l => chipHtml(l, lawCounts[l]||0)).join("");
  $("#sigChips").innerHTML = SIGNALS.filter(s => sigCounts[s]).map(s => chipHtml(s, sigCounts[s])).join("");
  const cats = [...new Set(DATA.map(d => d.category))].sort();
  $("#cat").innerHTML = '<option value="">出典すべて</option>' + cats.map(c => '<option>' + esc(c) + '</option>').join("");
  $("#lawChips").onclick = e => toggleChip(e, F.laws);
  $("#sigChips").onclick = e => toggleChip(e, F.sigs);
}

function toggleChip(e, set){
  const b = e.target.closest(".chip"); if(!b) return;
  const v = b.dataset.v;
  if(set.has(v)){ set.delete(v); b.setAttribute("aria-pressed","false"); }
  else { set.add(v); b.setAttribute("aria-pressed","true"); }
  render();
}

function renderKpis(){
  const rec = DATA.filter(d => daysAgo(d.published) <= 7).length;
  const nw = DATA.filter(d => d.is_new).length;
  const act = DATA.filter(d => d.signals.includes("法令改正") || d.signals.includes("意見公募")).length;
  const acc = DATA.filter(d => d.signals.includes("事故")).length;
  const k = [["新着（前回実行以降）", nw, 0], ["直近7日", rec, 0],
             ["法令改正・意見公募", act, 1], ["事故・災害", acc, 1], ["収録合計", DATA.length, 0]];
  $("#kpis").innerHTML = k.map(p =>
    '<div class="kpi' + (p[2] ? " flag" : "") + '"><b>' + p[1] + '</b><span>' + esc(p[0]) + '</span></div>').join("");
}

function activeFilterCount(){
  return F.laws.size + F.sigs.size + (F.q ? 1 : 0) + (F.cat ? 1 : 0)
    + (F.days !== 90 ? 1 : 0) + (F.onlyNew ? 1 : 0) + (F.onlyStar ? 1 : 0) + (F.onlyUnread ? 1 : 0);
}

function render(){
  const items = visible();
  const nf = activeFilterCount();
  $("#fcount").textContent = nf ? "（" + nf + "件適用中）" : "";
  $("#count").textContent = items.length + " 件を表示（全 " + DATA.length + " 件）";
  if(!items.length){ $("#list").innerHTML = '<li class="empty">条件に合う記事がありません。期間や法令の絞り込みを緩めてください。</li>'; return; }
  $("#list").innerHTML = items.map(it => {
    const c = lawColor(it);
    const badges = it.laws.map(l =>
      '<span class="badge law" style="--c:' + LAWMETA[l].color + '">' + esc(LAWMETA[l].short) + '</span>').join("");
    const sigs = it.signals.map(s => '<span class="badge sig">' + esc(s) + '</span>').join("");
    const nm = it.is_new ? '<span class="badge newmark">NEW</span>' : "";
    const kw = it.keywords.length ? "該当語: " + esc(it.keywords.join("・")) : "";
    const sum = it.summary ? esc(it.summary.slice(0,140)) : "";
    return '<li class="item' + (state.read[it.id] ? " read" : "") + '" data-id="' + it.id + '"'
      + (c ? ' style="--c:' + c + '"' : "") + '>'
      + '<div class="line1"><span class="date">' + (it.published || "日付不明") + '</span>' + nm + badges + sigs
      + '<span>' + esc(it.source_name) + (it.tag ? " ／ " + esc(it.tag) : "") + '</span></div>'
      + '<a class="title" href="' + esc(it.url) + '" target="_blank" rel="noopener">' + highlight(it.title, F.q) + '</a>'
      + '<div class="line3">' + sum + (sum && kw ? " ／ " : "") + kw + '</div>'
      + '<div class="acts">'
      + '<button class="iconbtn star' + (state.star[it.id] ? " on" : "") + '" title="ブックマーク" aria-label="ブックマーク">★</button>'
      + '<button class="iconbtn rd" title="既読/未読" aria-label="既読/未読">' + (state.read[it.id] ? "◉" : "○") + '</button>'
      + '</div></li>';
  }).join("");
}

$("#list").addEventListener("click", e => {
  const li = e.target.closest("li.item"); if(!li) return;
  const id = li.dataset.id;
  if(e.target.classList.contains("star")){ state.star[id] = !state.star[id]; save(); render(); }
  else if(e.target.classList.contains("rd")){ state.read[id] = !state.read[id]; save(); render(); }
  else if(e.target.classList.contains("title")){ state.read[id] = true; save(); setTimeout(render, 60); }
});

$("#q").oninput = e => { F.q = e.target.value.trim(); render(); };
$("#cat").onchange = e => { F.cat = e.target.value; render(); };
$("#days").onchange = e => { F.days = +e.target.value; render(); };
$("#sort").onchange = e => { F.sort = e.target.value; render(); };
[["#fNew","onlyNew"],["#fStar","onlyStar"],["#fUnread","onlyUnread"]].forEach(pair => {
  $(pair[0]).onclick = () => { F[pair[1]] = !F[pair[1]]; $(pair[0]).setAttribute("aria-pressed", String(F[pair[1]])); render(); };
});

// 画面が狭いときは絞り込みパネルを畳んでおき、ボタンで開閉する
const NARROW = window.matchMedia("(max-width:700px)");
function syncFold(){
  const collapse = NARROW.matches;
  $("#filters").classList.toggle("collapsed", collapse);
  $("#toggleFilters").setAttribute("aria-expanded", String(!collapse));
}
$("#toggleFilters").onclick = () => {
  const collapsed = $("#filters").classList.toggle("collapsed");
  $("#toggleFilters").setAttribute("aria-expanded", String(!collapsed));
};
NARROW.addEventListener("change", syncFold);

$("#reset").onclick = () => {
  F.laws.clear(); F.sigs.clear(); F.q=""; F.cat=""; F.days=90; F.sort="date";
  F.onlyNew=F.onlyStar=F.onlyUnread=false;
  document.querySelectorAll('.chip[aria-pressed]').forEach(c => c.setAttribute("aria-pressed","false"));
  $("#q").value=""; $("#cat").value=""; $("#days").value="90"; $("#sort").value="date"; render();
};

$("#copyMd").onclick = async () => {
  const rows = visible();
  const md = rows.map(it =>
    "- **" + (it.published || "日付不明") + "**［" + (it.laws.map(l => LAWMETA[l].short).join("/") || "-") + "］"
    + it.title + "  \n  " + it.source_name + " " + it.url
  ).join("\n");
  const text = "# 保安法令ニュース（" + TODAY + " 時点・" + rows.length + "件）\n\n" + md + "\n";
  try { await navigator.clipboard.writeText(text); $("#copyMd").textContent = "コピーしました"; }
  catch(e) { window.prompt("コピーしてください", text); }
  setTimeout(() => { $("#copyMd").textContent = "一覧をコピー"; }, 1800);
};

$("#dlCsv").onclick = () => {
  const q = s => '"' + String(s == null ? "" : s).replace(/"/g, '""') + '"';
  const rows = [["日付","法令","内容区分","出典","区分","タイトル","URL","重要度"].map(q).join(",")]
    .concat(visible().map(it => [it.published||"", it.laws.join("/"), it.signals.join("/"),
      it.source_name, it.category, it.title, it.url, it.score].map(q).join(",")));
  const blob = new Blob(["\uFEFF" + rows.join("\r\n")], {type:"text/csv;charset=utf-8"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = "保安法令ニュース_" + TODAY + ".csv"; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
};

$("#srcbody").innerHTML = SOURCES.map(s => '<tr>'
  + '<td>' + esc(s.name) + '</td><td>' + esc(s.category) + '</td>'
  + '<td class="num">' + s.fetched + '</td><td class="num">' + s.kept + '</td><td class="num">' + s.added + '</td>'
  + '<td class="' + (s.error && !s.skipped ? "err" : "") + '">' + (s.error ? esc(s.error) : "OK") + '</td></tr>').join("");

// --- 「最新に更新」ボタン ---
// serve.py 経由で開いているときだけ使える。ファイルを直接開いた場合や Artifact では
// 収集を実行する相手がいないので、応答を確かめてから初めてボタンを出す。
const UPD = $("#btnUpdate"), UPDS = $("#updStatus");

function setStatus(msg, bad){
  UPDS.textContent = msg;
  UPDS.classList.toggle("bad", !!bad);
}

async function probeUpdater(){
  if(IS_ARTIFACT || !/^https?:$/.test(location.protocol)) return;
  try {
    const r = await fetch("api/ping", {cache:"no-store"});
    if(r.ok) UPD.hidden = false;
  } catch(e) { /* 収集サーバーではない。ボタンは出さない */ }
}

UPD.onclick = async () => {
  UPD.disabled = true;
  UPD.textContent = "更新中…";
  setStatus("各サイトを巡回しています（20秒〜1分ほどかかります）");
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 300000);
  try {
    const r = await fetch("api/update", {method:"POST", cache:"no-store", signal:ctl.signal});
    const j = await r.json();
    if(!j.ok) throw new Error(j.error || "収集に失敗しました");
    setStatus("新着 " + j.added + " 件（収録 " + j.total + " 件）。読み込み直します…");
    setTimeout(() => location.reload(), 800);
  } catch(e) {
    UPD.disabled = false;
    UPD.textContent = "最新に更新";
    setStatus(e.name === "AbortError"
      ? "時間内に終わりませんでした。PC 側の画面を確認してください。"
      : "更新できませんでした: " + e.message, true);
  } finally {
    clearTimeout(timer);
  }
};

if(IS_ARTIFACT) $("#dlCsv").remove();

buildChips(); renderKpis(); syncFold(); render(); probeUpdater();
</script>
"""

STANDALONE = "\n".join([
    "<!doctype html>",
    '<html lang="ja">',
    "<head>",
    '<meta charset="utf-8">',
    TITLE,
    HEAD_EXTRA,
    "</head>",
    "<body>",
    "__BODY__",
    "</body>",
    "</html>",
    "",
])


def _json(obj) -> str:
    """<script> 内に安全に埋め込める JSON。"""
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def render_dashboard(
    out_path: Path,
    items: list[dict],
    source_stats: list[dict],
    law_meta: dict,
    signal_labels: list[str],
    prev_run: str | None,
    today: str,
    actions_url: str = "",
) -> Path:
    """dist/index.html（単体）と dist/artifact.html（本文のみ）を書き出す。

    actions_url が渡されたとき（GitHub 上で動かしているとき）は、
    自動更新されている旨と、手動で走らせるためのリンクを出す。
    """
    payload = [
        {
            "id": it["id"],
            "title": it["title"],
            "url": it["url"],
            "published": it.get("published") or "",
            "summary": it.get("summary") or "",
            "source_name": it["source_name"],
            "category": it["category"],
            "tag": it.get("tag") or "",
            "laws": it.get("laws", []),
            "signals": it.get("signals", []),
            "keywords": it.get("keywords", []),
            "score": it.get("score", 0),
            "is_new": bool(it.get("is_new")),
        }
        for it in items
    ]
    ok = sum(1 for s in source_stats if not s.get("error"))
    if actions_url:
        manual = ('  <a class="btn" href="' + actions_url + '" target="_blank" rel="noopener">'
                  "GitHub で今すぐ更新</a>")
        footnote = ("毎朝 8:00（日本時間）に自動で集め直しています。"
                    "すぐ更新したいときは上の「GitHub で今すぐ更新」から実行できます。")
    else:
        manual = ""
        footnote = ("更新するには <code>update.bat</code> をダブルクリック"
                    "（または <code>python main.py</code>）してください。")
    body = (
        BODY.replace("__DATA__", _json(payload))
        .replace("__SOURCES__", _json(source_stats))
        .replace("__LAWMETA__", _json(law_meta))
        .replace("__SIGNALS__", _json(signal_labels))
        .replace("__GENERATED__", datetime.now().strftime("%Y-%m-%d %H:%M"))
        .replace("__TOTAL__", str(len(payload)))
        .replace("__PREV__", (prev_run or "—").replace("T", " ")[:16])
        .replace("__TODAY__", today)
        .replace("__OKCOUNT__", str(ok))
        .replace("__SRCCOUNT__", str(len(source_stats)))
        .replace("__MANUAL__", manual)
        .replace("__FOOTNOTE__", footnote)
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        STANDALONE.replace("__BODY__", body.replace("__ARTIFACT__", "false")), encoding="utf-8"
    )
    # Artifact は <html>/<head>/<body> を自前で持てない。
    # 冒頭の <title> は公開時にページ名として読まれるので必ず先頭に置く。
    (out_path.parent / "artifact.html").write_text(
        TITLE + "\n" + body.replace("__ARTIFACT__", "true"), encoding="utf-8"
    )
    return out_path

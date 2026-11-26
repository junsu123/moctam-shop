// Màn hình diễn biến: đọc /api/state mỗi 2 giây và vẽ lại. Chỉ đọc; mọi chữ đưa vào trang qua textContent.
"use strict";

const TZ = "Asia/Ho_Chi_Minh";
const REFRESH_MS = 2000;
const fmtTime = new Intl.DateTimeFormat("vi-VN", { timeZone: TZ, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
const fmtShort = new Intl.DateTimeFormat("vi-VN", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hour12: false });
const fmtDay = new Intl.DateTimeFormat("vi-VN", { timeZone: TZ, day: "2-digit", month: "2-digit" });
const usd = (n) => (n ?? 0).toLocaleString("vi-VN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const STATUS_TEXT = {
  working: "đang làm", idle: "rảnh", waiting: "đang chờ", error: "vừa lỗi", paused: "tạm dừng", attention: "có việc chờ",
};
const OFFICE_TEXT = { running: "Văn phòng đang làm việc", paused: "Văn phòng đang tạm dừng", stopped: "Văn phòng đang nghỉ", new: "Văn phòng chưa làm việc lần nào", error: "Không đọc được sổ của văn phòng" };

let filter = "";
let seen = new Set();
let firstRender = true;
let lastState = null;

const $ = (id) => document.getElementById(id);
function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c !== null && c !== undefined) n.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return n;
}
const t = (iso) => (iso ? new Date(iso) : null);
function ago(iso, now) {
  if (!iso) return "";
  const s = Math.max(0, Math.round((now - t(iso)) / 1000));
  if (s < 60) return `${s} giây trước`;
  if (s < 3600) return `${Math.round(s / 60)} phút trước`;
  if (s < 86400) return `${Math.round(s / 3600)} giờ trước`;
  return `lúc ${fmtShort.format(t(iso))} ngày ${fmtDay.format(t(iso))}`;
}

function renderTop(s, now) {
  const o = s.office || {};
  document.body.dataset.state = o.state || "new";
  $("status-text").textContent = OFFICE_TEXT[o.state] || "Văn phòng AI";
  let sub = o.message || "";
  if (o.last_tick_at) sub = `Nhịp làm việc gần nhất ${ago(o.last_tick_at, now)} (${fmtTime.format(t(o.last_tick_at))}). ` + (o.state === "running" ? "" : sub);
  $("status-sub").textContent = sub;

  const facts = $("facts");
  facts.replaceChildren();
  const add = (label, value, warn) => facts.append(el("div", { class: warn ? "warn" : "" }, el("dt", { text: label }), el("dd", { text: value })));
  const l = s.llm || {};
  if (l.enabled === false) add("LLM", "chưa bật");
  else add(`Chi phí LLM hôm nay, trần ${usd(l.max_cost_usd)} USD`, `${usd(l.cost_usd)} USD`, l.cost_usd >= 0.8 * (l.max_cost_usd || 1));
  const b = s.backlog || {};
  const pending = (b.faq || 0) + (b.blog || 0) + (b.cross_sell || 0);
  add("Bản nháp chờ duyệt", String(pending));
  const esc = (s.escalations || []).length;
  add("Việc cần anh/chị", String(esc), esc > 0);
}

function renderLanes(s, now) {
  const box = $("lanes");
  box.replaceChildren();
  const span = (s.lane_minutes || 60) * 60000;
  const from = now - span;
  const agents = Object.fromEntries((s.agents || []).map((a) => [a.code, a]));
  for (const lane of s.lanes || []) {
    const a = agents[lane.code] || {};
    const track = el("div", { class: "track" });
    for (const b of lane.blocks) {
      const st = Math.max(t(b.start) - from, 0);
      const en = Math.min(Math.max(t(b.end) - from, st), span);
      const left = (st / span) * 100;
      const width = ((en - st) / span) * 100;
      const time = fmtShort.format(t(b.start));
      const tip = `${time} ${b.label}${b.summary ? ": " + b.summary : ""}`;
      const blk = el("span", { class: `blk ${b.status}`, title: tip, role: "img", "aria-label": tip });
      blk.style.left = `${left.toFixed(2)}%`;   // gán qua CSSOM để không vi phạm CSP
      blk.style.width = `${width.toFixed(2)}%`;
      track.append(blk);
    }
    const pressed = filter === lane.code;
    const sub = a.current ? a.current.label : (STATUS_TEXT[a.status] || "");
    box.append(el("button", { class: "lane", type: "button", "aria-pressed": pressed ? "true" : "false",
      onclick: () => setFilter(pressed ? "" : lane.code) },
      el("span", { class: "lane-name" }, lane.title, el("small", { text: sub })), track));
  }
}

function renderStaff(s, now) {
  const body = $("staff");
  body.replaceChildren();
  for (const a of s.agents || []) {
    let what;
    if (a.current) what = el("td", { class: "what" }, `Đang ${a.current.label}`, el("small", { text: `${a.current.reason ? a.current.reason + ". " : ""}Bắt đầu ${ago(a.current.since, now)}.` }));
    else if (a.last) what = el("td", { class: "what" }, `${a.last.status === "failed" ? "Lỗi khi" : "Vừa"} ${a.last.label}`,
      el("small", { text: [a.last.summary, ago(a.last.at, now)].filter(Boolean).join(", ") }));
    else what = el("td", { class: "what" }, el("small", { text: a.note || "Chưa có việc nào" }));
    if (a.note && (a.current || a.last) && a.status === "waiting") what.append(el("small", { text: `Đang chờ: ${a.note}` }));
    if (a.code === "chu_xuong" || a.code === "truong_phong") { what.replaceChildren(document.createTextNode(a.note || ""));
      if (a.code === "truong_phong" && a.last) what.append(el("small", { text: `${a.last.summary}, ${ago(a.last.at, now)}` })); }
    const today = a.code === "chu_xuong" ? "" : (a.today.failed ? el("span", {}, `${a.today.done} xong, `, el("span", { class: "bad", text: `${a.today.failed} lỗi` })) : `${a.today.done} xong`);
    body.append(el("tr", {},
      el("td", {}, a.title, el("small", { text: a.duty })),
      el("td", {}, el("span", { class: `tag ${a.status}`, text: STATUS_TEXT[a.status] || a.status })),
      what,
      el("td", { class: "num" }, today)));
  }
}

function renderWaiting(s, now) {
  const ul = $("waiting");
  ul.replaceChildren();
  const items = s.waiting || [];
  if (!items.length) { ul.append(el("li", { class: "empty", text: "Không có việc nào bị hoãn hay chặn trong 24 giờ qua." })); return; }
  for (const w of items.slice(0, 12)) {
    ul.append(el("li", {},
      el("span", { class: "who", text: w.role_title }),
      el("span", {}, el("span", { class: `v-${w.verdict}`, text: w.verdict === "block" ? "Chặn " : "Hoãn " }), `${w.label}: ${w.why}`),
      el("span", { class: "when", text: ago(w.at, now) })));
  }
}

function renderEscalations(s, now) {
  const ul = $("escalations");
  ul.replaceChildren();
  const items = s.escalations || [];
  if (!items.length) { ul.append(el("li", { class: "empty", text: "Không có việc nào cần anh/chị lúc này." })); ul.firstChild.style.background = "none"; ul.firstChild.style.border = "0"; return; }
  for (const e of items) {
    ul.append(el("li", { class: e.severity < 0.5 ? "low" : "" },
      el("b", { text: e.title }), e.detail ? el("p", { text: e.detail }) : null, el("span", { class: "since", text: `Từ ${ago(e.since, now)}` })));
  }
}

function renderFeed(s) {
  const sel = $("filter");
  if (sel.options.length <= 1) for (const a of s.agents || []) sel.append(el("option", { value: a.code, text: a.title }));
  sel.value = filter;
  const ol = $("feed");
  ol.replaceChildren();
  const items = (s.feed || []).filter((f) => !filter || f.role === filter);
  if (!items.length) { ol.append(el("li", { class: "empty", text: "Chưa có diễn biến nào trong 24 giờ qua." })); return; }
  for (const f of items.slice(0, 120)) {
    const key = `${f.at}|${f.role}|${f.kind}|${f.text}`;
    const fresh = !firstRender && !seen.has(key);
    seen.add(key);
    ol.append(el("li", { class: `${f.kind}${fresh ? " new" : ""}` },
      el("time", { datetime: f.at, text: fmtTime.format(t(f.at)) }),
      el("span", {}, el("span", { class: "who", text: f.role_title }), " ", el("span", { class: "what", text: f.text })),
      f.detail ? el("span", { class: "detail", text: f.detail }) : null));
  }
  if (seen.size > 5000) seen = new Set([...seen].slice(-2000));
}

function setFilter(code) {
  filter = code;
  if (lastState) render(lastState);
}

function render(s) {
  const now = Date.now();
  renderTop(s, now);
  renderLanes(s, now);
  renderStaff(s, now);
  renderWaiting(s, now);
  renderEscalations(s, now);
  renderFeed(s);
  firstRender = false;
}

async function refresh() {
  try {
    const r = await fetch("/api/state", { cache: "no-store" });
    const s = await r.json();
    if (!r.ok) throw new Error(s.error || r.statusText);
    $("banner").hidden = true;
    lastState = s;
    render(s);
  } catch (e) {
    const b = $("banner");
    b.hidden = false;
    b.textContent = `Không đọc được trạng thái văn phòng (${e.message}). Màn hình sẽ tự thử lại.`;
    document.body.dataset.state = "error";
  } finally {
    setTimeout(refresh, REFRESH_MS);
  }
}

$("filter").addEventListener("change", (e) => setFilter(e.target.value));
refresh();

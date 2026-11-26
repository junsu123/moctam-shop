"""Màn hình diễn biến trực tiếp: chỉ đọc, đủ thông tin từng nhân viên, an toàn."""
import json
import sqlite3
import urllib.request

from xuong_ai import monitor

from .test_brain import mk, run_ticks  # noqa: F401  (mk là fixture)


def _ro(path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def test_state_shows_each_agent_feed_and_lanes(mk, tmp_path):
    b, site = mk()
    run_ticks(b, 2)
    b.store.db.execute("INSERT INTO brain_tasks(key, action, role, goal, params, reason, status, started_at) "
                       "VALUES('blog:x','blog_draft','bien_tap','noi_dung_seo','{}','Trà hoa cúc chưa có bài','running', datetime('now'))")
    path = tmp_path / "o.sqlite3"
    b.store.db.execute(f"VACUUM INTO '{path}'")
    s = monitor.build_state(_ro(path), b.cfg)
    assert s["office"]["state"] == "running"
    agents = {a["code"]: a for a in s["agents"]}
    assert set(agents) == {"truong_phong", "thu_ky", "tu_van", "bien_tap", "cham_soc", "phan_tich", "ky_thuat", "chu_xuong"}
    assert agents["bien_tap"]["status"] == "working" and agents["bien_tap"]["current"]["label"] == "soạn bài blog"
    assert agents["thu_ky"]["today"]["done"] >= 2 and agents["thu_ky"]["last"]["status"] == "done"
    assert agents["tu_van"]["last"]["summary"].startswith("Đã gửi lên website chờ duyệt")
    assert agents["chu_xuong"]["status"] == "attention"  # có câu hỏi dị ứng chờ người
    kinds = {f["kind"] for f in s["feed"]}
    assert {"start", "done", "escalate", "llm"} <= kinds
    assert s["feed"] == sorted(s["feed"], key=lambda f: f["at"], reverse=True)
    lanes = {l["code"]: l for l in s["lanes"]}
    assert "chu_xuong" not in lanes and any(x["status"] == "running" for x in lanes["bien_tap"]["blocks"])
    assert any(x["status"] == "tick" for x in lanes["truong_phong"]["blocks"])


def test_waiting_and_stopped_office(mk, tmp_path):
    b, site = mk(max_pending_review=0)
    run_ticks(b, 2)
    b.store.db.execute("UPDATE brain_ticks SET started_at = datetime('now','-2 hours'), finished_at = datetime('now','-2 hours')")
    path = tmp_path / "o.sqlite3"
    b.store.db.execute(f"VACUUM INTO '{path}'")
    s = monitor.build_state(_ro(path), b.cfg)
    assert s["office"]["state"] == "stopped" and "python -m xuong_ai run" in s["office"]["message"]
    assert any("chờ duyệt" in w["why"] for w in s["waiting"])
    assert {a["code"]: a for a in s["agents"]}["tu_van"]["status"] == "waiting"


def test_new_office_and_readonly(mk, tmp_path):
    con = sqlite3.connect(tmp_path / "empty.sqlite3")
    con.execute("CREATE TABLE x(a)")
    con.close()
    b, _ = mk()
    s = monitor.build_state(_ro(tmp_path / "empty.sqlite3"), b.cfg)
    assert s["office"]["state"] == "new"
    # dựng trạng thái không ghi gì
    run_ticks(b, 1)
    path = tmp_path / "o.sqlite3"
    b.store.db.execute(f"VACUUM INTO '{path}'")
    before = path.read_bytes()
    monitor.build_state(_ro(path), b.cfg)
    assert path.read_bytes() == before


def test_summaries():
    assert monitor.summarize("sync", json.dumps({"applied": 0}), None) == "Không có thay đổi mới"
    assert monitor.summarize("catalog", json.dumps({"products": 2, "faqs": 1, "unanswered": 3}), None).startswith("2 sản phẩm")
    assert monitor.summarize("feedback", json.dumps({"changed": {"rejected": 1}}), None) == "Kết quả duyệt mới: 1 từ chối"
    assert monitor.summarize("crosssell", None, "Website trả lỗi 503").startswith("Lỗi: Website")


def test_http_server_localhost_readonly_and_csp(mk, tmp_path):
    b, site = mk()
    run_ticks(b, 1)
    path = tmp_path / "o.sqlite3"
    b.store.db.execute(f"VACUUM INTO '{path}'")
    b.cfg.db_path = path
    srv, url = monitor.serve(b.cfg, port=0, background=True)
    try:
        assert url.startswith("http://127.0.0.1:")
        r = urllib.request.urlopen(url + "/")
        html = r.read().decode()
        assert "Diễn biến" in html and "script-src" not in html
        assert "default-src 'self'" in r.headers["Content-Security-Policy"]
        st = json.loads(urllib.request.urlopen(url + "/api/state").read())
        assert st["office"]["state"] == "running" and st["agents"]
        for p in ("/app.js", "/app.css", "/favicon.svg"):
            assert urllib.request.urlopen(url + p).status == 200
        req = urllib.request.Request(url + "/api/state", method="POST", data=b"{}")
        try:
            urllib.request.urlopen(req)
            raise AssertionError("POST phải bị từ chối")
        except urllib.error.HTTPError as e:
            assert e.code == 501
        # không lộ dữ liệu cá nhân: CSDL cục bộ không có, và API không thêm trường nào như vậy
        assert not any(k in json.dumps(st, ensure_ascii=False) for k in ("phone", "address", "email"))
    finally:
        srv.shutdown()
        srv.server_close()

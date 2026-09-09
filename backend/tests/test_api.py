# tests/test_api.py
"""API 层冒烟：认证/RBAC/上传发布/检索/评测/反馈。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import login

MD = "# 并网管理\n\n分布式光伏并网前应完成接入系统方案确认，并网验收合格后方可并网运行。电网企业不得无正当理由拒绝户用光伏并网。\n\n# 安全\n\n项目应配置防孤岛保护与防雷接地。\n"


def _editor_headers(client: TestClient) -> dict:
    token = login(client, "editor")["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_login_and_me(api):
    client, _db, _rt = api
    data = login(client, "admin")
    assert data["token_type"] == "bearer"
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert me.status_code == 200
    assert me.json()["role"] == "admin"


def test_upload_publish_and_search(api):
    client, _db, _rt = api
    h = _editor_headers(client)
    up = client.post(
        "/api/v1/documents/upload",
        headers=h,
        data={
            "title": "分布式光伏并网办法测试",
            "doc_code": "国能发测试〔2025〕1号",
            "doc_type": "grid_connection",
            "issuing_body": "国家能源局",
            "issue_year": "2025",
            "publish": "true",
        },
        files={"file": ("policy.md", MD.encode("utf-8"), "text/markdown")},
    )
    assert up.status_code == 200, up.text
    body = up.json()
    assert body["indexed"] is True
    doc_id = body["document"]["id"]

    s = client.get("/api/v1/search", headers=h, params={"q": "分布式光伏并网需要什么手续", "top_k": 3})
    assert s.status_code == 200
    hits = s.json()["hits"]
    assert len(hits) >= 1
    assert hits[0]["doc_code"] == "国能发测试〔2025〕1号"

    lst = client.get("/api/v1/documents", headers=h, params={"keyword": "分布式"})
    assert lst.json()["total"] >= 1
    pv = client.get(f"/api/v1/documents/{doc_id}/preview", headers=h)
    assert "并网" in pv.json()["text"]


def test_viewer_cannot_publish(api):
    client, _db, _rt = api
    editor_h = _editor_headers(client)
    up = client.post(
        "/api/v1/documents/upload",
        headers=editor_h,
        data={"title": "权限测试文档", "doc_type": "other", "publish": "false"},
        files={"file": ("a.md", MD.encode("utf-8"), "text/markdown")},
    ).json()
    doc_id = up["document"]["id"]
    viewer_token = login(client, "viewer")["access_token"]
    resp = client.post(
        f"/api/v1/documents/{doc_id}/publish",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={},
    )
    assert resp.status_code == 403


def test_eval_roundtrip(api):
    client, _db, _rt = api
    h = _editor_headers(client)
    client.post(
        "/api/v1/documents/upload",
        headers=h,
        data={"title": "平价上网政策", "doc_code": "电价政策-X", "doc_type": "tariff_subsidy", "publish": "true"},
        files={"file": ("t.md", "# 电价\n\n新备案集中式光伏实行平价上网，不再补贴。\n".encode(), "text/markdown")},
    )
    cs = client.post(
        "/api/v1/eval/sets",
        headers=h,
        json={
            "name": "临时评测",
            "cases": [
                {
                    "question": "新备案集中式光伏还有固定补贴吗",
                    "golden_doc_codes": ["电价政策-X"],
                    "golden_keywords": ["平价上网", "补贴"],
                }
            ],
        },
    )
    assert cs.status_code == 200, cs.text
    run = client.post(
        "/api/v1/eval/runs", headers=h, json={"eval_set_id": 1, "top_k": 3, "generate": False}
    )
    assert run.status_code == 200, run.text
    assert run.json()["case_count"] >= 1


def test_qa_stream_done_frame(api):
    client, _db, _rt = api
    h = _editor_headers(client)
    # 空库（未发布文档）时也应返回结构化的 SSE done 帧而非挂死
    with client.stream("POST", "/api/v1/chat/stream", headers=h, json={"question": "光伏电价补贴政策"}) as resp:
        assert resp.status_code == 200
        text = "".join(resp.iter_text())
    assert "event:" in text
    assert "done" in text or "error" in text

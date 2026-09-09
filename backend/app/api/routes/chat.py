# app/api/routes/chat.py
"""SSE 流式问答接口。"""
from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import DbDep, RuntimeDep, UserDep
from app.repositories import qa_repo
from app.schemas.common import Message
from app.services.qa_service import QaService

router = APIRouter(tags=["问答"])


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000, description="问题")


class FeedbackBody(BaseModel):
    feedback: int = Field(..., ge=-1, le=1, description="1 有帮助 / -1 无帮助")


def _sse_frame(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
def chat_stream(payload: ChatRequest, user: UserDep, runtime: RuntimeDep):
    """SSE：meta → delta* → done|error。"""

    def gen() -> Iterator[str]:
        yield ": connected\n\n"
        try:
            for ev in QaService(runtime).stream_qa(user.id, payload.question):
                event = ev.pop("type", "message")
                yield _sse_frame(event, ev)
        except Exception as exc:  # noqa: BLE001
            yield _sse_frame("error", {"message": f"问答服务异常：{exc}"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/chat/history")
def history(
    db: DbDep,
    user: UserDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    total, rows = qa_repo.list_qa_logs(db, user_id=user.id, page=page, page_size=page_size)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [qa_repo.qa_log_to_dict(r) for r in rows],
    }


@router.post("/chat/{log_id}/feedback", response_model=Message)
def feedback(log_id: int, body: FeedbackBody, db: DbDep, user: UserDep) -> dict:
    ok = qa_repo.set_feedback(db, log_id, body.feedback)
    if not ok:
        from app.core.errors import NotFoundError

        raise NotFoundError("问答记录不存在")
    db.commit()
    return {"message": "已记录反馈"}

# app/api/routes/eval.py
"""RAG 评测接口。"""
from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.deps import DbDep, EditorDep, RuntimeDep, UserDep
from app.repositories import eval_repo
from app.schemas.common import Message
from app.services.eval_service import EvalService

router = APIRouter(tags=["评测"])


class EvalSetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="")
    cases: list[dict] = Field(default_factory=list)


class RunEvalBody(BaseModel):
    eval_set_id: int
    top_k: int = Field(5, ge=1, le=20)
    generate: bool = Field(False, description="是否对每条执行 LLM 生成以评测引用忠实度")


@router.get("/eval/sets")
def list_sets(db: DbDep, _: UserDep) -> dict:
    sets = eval_repo.list_sets(db)
    return {"items": [eval_repo.set_to_dict(s) for s in sets]}


@router.post("/eval/sets", response_model=Message)
def create_set(payload: EvalSetCreate, db: DbDep, user: EditorDep) -> dict:
    s = eval_repo.create_set(
        db, name=payload.name, description=payload.description, created_by=user.id
    )
    added = eval_repo.add_cases(db, s.id, payload.cases)
    db.commit()
    return {"message": f"评测集已创建（含 {added} 条题目）"}


@router.get("/eval/sets/{set_id}/cases")
def cases(set_id: int, db: DbDep, _: UserDep) -> dict:
    cs = eval_repo.cases_of(db, set_id)
    return {
        "eval_set_id": set_id,
        "count": len(cs),
        "cases": [
            {
                "id": c.id,
                "question": c.question,
                "golden_doc_codes": c.golden_doc_codes,
                "golden_keywords": c.golden_keywords,
                "category": c.category,
            }
            for c in cs
        ],
    }


@router.post("/eval/runs")
def run_eval(body: RunEvalBody, db: DbDep, runtime: RuntimeDep, user: EditorDep) -> dict:
    return EvalService(runtime).run(
        db,
        eval_set_id=body.eval_set_id,
        top_k=body.top_k,
        generate=body.generate,
        operator_id=user.id,
    )


@router.get("/eval/runs")
def list_runs(db: DbDep, _: UserDep, limit: int = Query(30, ge=1, le=100)) -> dict:
    return {"items": [eval_repo.run_to_dict(r) for r in eval_repo.list_runs(db, limit)]}


@router.get("/eval/runs/{run_id}")
def run_detail(run_id: int, db: DbDep, _: UserDep) -> dict:
    r = eval_repo.get_run(db, run_id)
    if not r:
        from app.core.errors import NotFoundError

        raise NotFoundError("评测运行不存在")
    return eval_repo.run_to_dict(r)

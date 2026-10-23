# app/repositories/eval_repo.py
"""评测集/评测运行 仓储。"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EvalCase, EvalRun, EvalSet


# ---------- 评测集 ----------
def create_set(db: Session, *, name: str, description: str, created_by: int | None) -> EvalSet:
    s = EvalSet(name=name, description=description, created_by=created_by)
    db.add(s)
    db.flush()
    return s


def list_sets(db: Session) -> list[EvalSet]:
    return list(db.execute(select(EvalSet).order_by(EvalSet.id)).scalars())


def get_set(db: Session, set_id: int) -> EvalSet | None:
    return db.execute(select(EvalSet).where(EvalSet.id == set_id)).scalar_one_or_none()


def add_cases(db: Session, eval_set_id: int, cases: list[dict]) -> int:
    for c in cases:
        db.add(
            EvalCase(
                eval_set_id=eval_set_id,
                question=c["question"],
                golden_doc_codes=c.get("golden_doc_codes", []),
                golden_keywords=c.get("golden_keywords", []),
                category=c.get("category", ""),
                notes=c.get("notes", ""),
            )
        )
    db.flush()
    return len(cases)


def cases_of(db: Session, eval_set_id: int) -> list[EvalCase]:
    return list(
        db.execute(select(EvalCase).where(EvalCase.eval_set_id == eval_set_id).order_by(EvalCase.id)).scalars()
    )


def set_to_dict(s: EvalSet) -> dict[str, Any]:
    return {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "case_count": len(s.cases),
        "created_at": s.created_at.isoformat(),
    }


# ---------- 评测运行 ----------
def create_run(db: Session, **fields: Any) -> EvalRun:
    r = EvalRun(**fields)
    db.add(r)
    db.flush()
    return r


def list_runs(db: Session, limit: int = 30) -> list[EvalRun]:
    return list(db.execute(select(EvalRun).order_by(EvalRun.id.desc()).limit(limit)).scalars())


def get_run(db: Session, run_id: int) -> EvalRun | None:
    return db.execute(select(EvalRun).where(EvalRun.id == run_id)).scalar_one_or_none()


def run_to_dict(r: EvalRun) -> dict[str, Any]:
    return {
        "id": r.id,
        "eval_set_id": r.eval_set_id,
        "name": r.name,
        "params": r.params,
        "case_count": r.case_count,
        "hit_rate": r.hit_rate,
        "hit_rate_top1": r.hit_rate_top1,
        "context_recall": r.context_recall,
        "citation_precision": r.citation_precision,
        "details": r.details,
        "created_at": r.created_at.isoformat(),
    }

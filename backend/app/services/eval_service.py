# app/services/eval_service.py
"""RAG 评测闭环：命中率 / 上下文召回率 / 引用忠实度 回归。

- hit_rate：Top-K 结果是否命中黄金文号/黄金条款（召回@K）。
- hit_rate_top1：首条命中比例。
- context_recall：黄金关键词在召回上下文中的覆盖率均值。
- faithfulness：生成答案的 [n] 引用均指向黄金文号的比例（generate=True 时计算；
  该指标需要 LLM 参与，可能较慢）。
"""
from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationFailed
from app.models import EvalRun
from app.providers.registry import RagRuntime
from app.repositories import eval_repo
from app.retrieval.text_utils import ascii_letters
from app.services.qa_service import QaService
from app.services.retrieval_service import SearchService

logger = logging.getLogger(__name__)
_CITE = re.compile(r"\[(\d{1,3})\]")


def _norm_code(s: str) -> str:
    return ascii_letters(s or "")


class EvalService:
    def __init__(self, runtime: RagRuntime) -> None:
        self.rt = runtime
        self.search = SearchService(runtime)
        self._last_answer: str | None = None

    def _case_metrics(
        self, db: Session, question: str, golden_codes: list[str], golden_keywords: list[str], top_k: int
    ) -> tuple[dict[str, Any], list[str], str | None]:
        """返回 (case_detail, retrieved_texts, top1_code)。"""
        ctx = self.search.search(db, question, top_k=top_k)
        doc_codes = [it.meta.doc_code for it in ctx.items]
        texts = [it.text for it in ctx.items]
        combined = "\n".join(texts)
        gcodes = {_norm_code(c) for c in golden_codes if c}
        hit = False
        if gcodes:
            hit = any(_norm_code(c) in {_norm_code(d) for d in doc_codes} for c in gcodes)
        else:
            hit = any(kw and kw in combined for kw in golden_keywords)
        top1_hit = False
        if ctx.items:
            first_code = _norm_code(ctx.items[0].meta.doc_code)
            top1_hit = bool(gcodes) and first_code in {_norm_code(c) for c in golden_codes} or (
                not gcodes and any(kw and kw in ctx.items[0].text for kw in golden_keywords)
            )
        present_kws = [kw for kw in golden_keywords if kw and kw in combined]
        recall = len(present_kws) / len(golden_keywords) if golden_keywords else None
        detail: dict[str, Any] = {
            "question": question,
            "top_doc_codes": doc_codes[:top_k],
            "hit": hit,
            "top1_hit": top1_hit,
            "keywords_found": present_kws,
            "recall": recall,
        }
        return detail, texts, (ctx.items[0].meta.doc_code if ctx.items else None)

    def _faithfulness(
        self, question: str, golden_codes: list[str], messages: list[dict], citations: list[dict]
    ) -> float | None:
        """引用忠实度 = 生成答案引用的[来源]中指向黄金文号的比例（无引用记 0）。"""
        try:
            answer = self.rt.llm.complete(messages)
        except Exception as exc:  # noqa: BLE001
            logger.warning("faithfulness 生成失败: %s", exc)
            self._last_answer = None
            return None
        self._last_answer = answer
        refs = [int(x) for x in _CITE.findall(answer)]
        if not refs:
            return 0.0
        gcodes = {_norm_code(c) for c in golden_codes if c}
        if not gcodes:
            return None  # 无黄金文号可判，不参与统计
        cited_codes = {
            _norm_code(c["doc_code"])
            for r in refs
            if 1 <= r <= len(citations)
            for c in [citations[r - 1]]
        }
        if not cited_codes:
            return 0.0
        return round(len(cited_codes & gcodes) / len(cited_codes), 4)

    def run(
        self,
        db: Session,
        *,
        eval_set_id: int,
        top_k: int = 5,
        generate: bool = False,
        operator_id: int | None = None,
    ) -> dict:
        es = eval_repo.get_set(db, eval_set_id)
        if not es:
            raise NotFoundError("评测集不存在")
        cases = eval_repo.cases_of(db, eval_set_id)
        if not cases:
            raise ValidationFailed("评测集为空，请先补充题目")
        qa = QaService(self.rt)

        details: list[dict] = []
        n_hit = n_hit1 = 0
        recall_vals: list[float] = []
        faithfulness_vals: list[float] = []
        for case in cases:
            detail, _texts, _top1 = self._case_metrics(
                db, case.question, list(case.golden_doc_codes or []), list(case.golden_keywords or []), top_k
            )
            n_hit += int(detail["hit"])
            n_hit1 += int(detail["top1_hit"])
            if detail["recall"] is not None:
                recall_vals.append(detail["recall"])
            if generate:
                # 生成需要重建上下文，走 QA 消息模板
                ctx = self.search.search(db, case.question, top_k=top_k)
                citations = ctx.citations()
                messages = qa.build_messages(ctx, case.question)
                f = self._faithfulness(
                    case.question, list(case.golden_doc_codes or []), messages, citations
                )
                if f is not None:
                    faithfulness_vals.append(f)
                detail["faithfulness"] = f
                detail["answer"] = self._last_answer
                # 附带每条目内容以支撑对账
                detail["retrieved"] = list(citations)
            details.append(detail)

        n = len(cases)
        run: EvalRun = eval_repo.create_run(
            db,
            eval_set_id=eval_set_id,
            name=es.name,
            params={"top_k": top_k, "generate": generate, "model": self.rt.llm.model},
            case_count=n,
            hit_rate=round(n_hit / n, 4),
            hit_rate_top1=round(n_hit1 / n, 4),
            context_recall=round(sum(recall_vals) / len(recall_vals), 4) if recall_vals else 0.0,
            faithfulness=round(sum(faithfulness_vals) / len(faithfulness_vals), 4)
            if faithfulness_vals
            else None,
            details=details,
            created_by=operator_id,
        )
        db.commit()
        return eval_repo.run_to_dict(run)

# app/services/qa_service.py
"""检索增强问答：检索锁定材料 → 逐句[来源]引用的接地生成（SSE 流式）。"""
from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator
from typing import Any

from app.core.database import SessionLocal
from app.providers.registry import RagRuntime
from app.repositories import qa_repo
from app.services.retrieval_service import SearchContext, SearchService

logger = logging.getLogger(__name__)

_CITE = re.compile(r"\[(\d{1,3})\]")


class QaService:
    def __init__(self, runtime: RagRuntime) -> None:
        self.rt = runtime
        self.search = SearchService(runtime)

    # ---------- 提示词构建 ----------
    def _materials(self, ctx: SearchContext) -> tuple[str, list[dict]]:
        citations = ctx.citations()
        lines: list[str] = []
        for i, it in enumerate(ctx.items, start=1):
            m = it.meta
            excerpt = it.text[:600] + ("…" if len(it.text) > 600 else "")
            head = f"《{m.title}》"
            if m.doc_code:
                head = f"{m.doc_code}《{m.title}》"
            lines.append(
                f"[{i}] 出处：{head}（类型：{m.doc_type}，{m.issuing_body}，"
                f"{m.issue_year or '年份不详'}）；章节：{m.section_path or '全文'}\n    原文：{excerpt}"
            )
        return "\n\n".join(lines), citations

    def build_messages(self, ctx: SearchContext, question: str) -> list[dict]:
        materials, _ = self._materials(ctx)
        system = (
            "你是「光溯」，光伏电站建设政策与规范智能问答助手。请严格依据下方给出的【检索材料】回答用户问题：\n"
            "1. 结论与判断必须来自材料原文，逐句/逐要点在其后标注材料编号，格式为 [1]、[2] 等；\n"
            "2. 禁止编造材料中不存在的文号、条款或要求；不得引用材料之外的任何政策；\n"
            "3. 若材料不足以可靠作答，明确回答“知识库未覆盖该问题或依据已失效，建议人工核实”；\n"
            "4. 当问题涉及失效/废止依据时，以检索到现行有效条文为准并提示。\n"
            "5. 语言精炼、分点作答，默认中文。"
        )
        user = f"【检索材料】\n{materials or '（无）'}\n\n【问题】\n{question}\n\n请作答："
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    @staticmethod
    def grounded(answer: str, n_sources: int) -> bool:
        if not answer or n_sources <= 0:
            return False
        refs = [int(x) for x in _CITE.findall(answer)]
        return any(1 <= r <= n_sources for r in refs)

    # ---------- 流式问答 ----------
    def stream_qa(self, user_id: int | None, question: str) -> Iterator[dict[str, Any]]:
        t0 = time.perf_counter()
        db = SessionLocal()
        try:
            ctx = self.search.search(db, question)
            rewrite = ctx.rewrite.summary() if ctx.rewrite else {}
            citations = ctx.citations()
            yield {"type": "meta", "rewritten": rewrite, "citations": citations, "count": len(ctx.items)}

            if not ctx.items:
                db.commit()
                yield {
                    "type": "done",
                    "text": "知识库中未检索到与问题相关的**已发布有效**依据。建议：① 换一种表述；② 确认该政策是否已被归档；③ 在“文档库”中补充/发布对应政策后再试。",
                    "grounded": False,
                    "empty": True,
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    "qa_log_id": None,
                }
                return

            messages = self.build_messages(ctx, question)
            full: list[str] = []
            try:
                for piece in self.rt.llm.stream(messages):
                    full.append(piece)
                    yield {"type": "delta", "text": piece}
            except Exception as exc:  # noqa: BLE001
                logger.warning("生成流中断: %s", exc)
                full.append("\n\n> ⚠️ 生成服务异常，已展示当前检索结果摘要。")
                for i, c in enumerate(citations, start=1):
                    full.append(f"[{i}] {c['doc_code'] or c['title']}·{c.get('section_path') or ''}")
                yield {"type": "delta", "text": "\n\n（以上为检索到的主要依据，供参考）"}

            answer = "".join(full)
            grounded = self.grounded(answer, len(citations))
            log = qa_repo.add_qa_log(
                db,
                user_id=user_id,
                question=question,
                rewritten_query=rewrite.get("expanded", ""),
                answer=answer,
                sources=citations,
                model=self.rt.llm.model,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                grounded=grounded,
            )
            db.commit()
            yield {
                "type": "done",
                "text": answer,
                "grounded": grounded,
                "qa_log_id": log.id,
                "latency_ms": int((time.perf_counter() - t0) * 1000),
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("问答链路异常")
            db.rollback()
            yield {"type": "error", "message": f"问答服务异常：{exc}"}
        finally:
            db.close()

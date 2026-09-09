# app/scripts/seed_demo.py
"""灌入演示语料库与评测集。

用法（在 backend/ 下，依赖已装好）：
    python -m app.scripts.seed_demo --corpus samples/corpus --eval samples/eval_demo.json
"""
from __future__ import annotations

import argparse

from app.core.config import get_settings
from app.core.database import SessionLocal, create_all
from app.core.logging import setup_logging
from app.providers.registry import build_runtime
from app.services.seed_service import seed_demo, seed_eval_demo


def main() -> None:
    setup_logging()
    settings = get_settings()
    create_all()
    parser = argparse.ArgumentParser(description="光溯演示数据种子")
    parser.add_argument("--corpus", default=str(settings.samples_dir / "corpus"))
    parser.add_argument("--eval", default=str(settings.samples_dir / "eval_demo.json"))
    parser.add_argument("--no-eval", action="store_true", help="跳过评测集")
    args = parser.parse_args()

    runtime = build_runtime(settings)
    db = SessionLocal()
    try:
        corpus = seed_demo(db, runtime, __import__("pathlib").Path(args.corpus))
        print(f"[seed] 语料库：{corpus}")
        if not args.no_eval:
            ev = seed_eval_demo(db, __import__("pathlib").Path(args.eval))
            print(f"[seed] 评测集：{ev}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

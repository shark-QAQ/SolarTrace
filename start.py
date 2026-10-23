# -*- coding: utf-8 -*-
"""SolarTrace（光溯）一键启动脚本 —— 前后端本地一键起。

设计目标（对齐仓库“工程隔离 / uv 管理 / 不污染本机”）：
  1. 只用仓库内 **uv 管理的 venv**（backend/.venv）跑后端；从未创建时才以
     `uv sync` 在该 venv 内装依赖，绝不写入系统 Python / 全局 site-packages。
  2. 前端直接复用 frontend/node_modules（缺失时才以 `npm install` 装到项目内，
     不改动全局）。node_modules 已在仓库本地。
  3. 演示语料按需幂等灌入（idempotent seed），灌入使用的嵌入/生成 provider 与
     后端运行保持一致，避免“用 hash 建索引、却用 bge-m3 检索”这类错配。
  4. Ctrl+C / 异常退出时自动回收两个子进程。

用法（仓库根目录，任选其一）：
    python start.py                 # 自动探测 Ollama：在线(bge-m3+qwen2.5)或离线(hash/fake)
    python start.py --offline       # 强制离线链路演示（无 Ollama/无模型也能起）
    python start.py --online        # 强制在线（需本地 Ollama 且装有 bge-m3 / qwen2.5:7b）
    python start.py --seed          # 强制重灌演示语料（幂等）
    python start.py --no-seed       # 跳过一切灌语料动作，直接起服务
    python start.py --no-frontend   # 仅起后端
    python start.py --backend-port 8001 --frontend-port 5173

启动后：
    前端  http://localhost:5173    （/api 由 Vite 代理到后端）
    后端  http://localhost:8000    （接口文档 /docs）
    登录  默认 admin / admin123
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Windows 控制台/管道统一按 UTF-8 输出，避免 GBK 下中文乱码或编码异常
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001   # 非文本流或旧 Python 时忽略
        pass

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
DATA_DIR = BACKEND / "data"
SEED_MARKER = DATA_DIR / ".seed_profile"      # 记录上次灌语料用的 provider 档位

WINDOWS = os.name == "nt"
SYSTEM_IS_WIN = sys.platform.startswith("win")

# 默认端口
BACKEND_PORT = 8000
FRONTEND_PORT = 5173

# 后端 venv 里 python 可执行文件路径（Windows/Linux/macOS）
def venv_python(bindir: str = "Scripts" if SYSTEM_IS_WIN else "bin") -> Path:
    exe = "python.exe" if SYSTEM_IS_WIN else "python"
    return BACKEND / ".venv" / bindir / exe


def log(msg: str) -> None:
    print(f"[start] {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"[start][warn] {msg}", flush=True)


# --------------------------------------------------------------------------- #
# 1) 环境探测
# --------------------------------------------------------------------------- #
def _read_env_file(path: Path) -> dict[str, str]:
    """极简解析 .env（形如 KEY=VALUE，# 注释）。"""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def ollama_models(settings_env: dict[str, str]) -> list[str]:
    """探测本机 Ollama 模型；不可达返回 []。"""
    base = settings_env.get("SOLARTRACE_OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=2) as r:  # noqa: S310
            import json

            data = json.load(r)
            return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return []


def choose_profile(args: argparse.Namespace, settings_env: dict[str, str]) -> tuple[str, dict[str, str]]:
    """返回 (profile, extra_env)。profile ∈ {online, offline}。

    尊重 backend/.env 里用户显式写死的 provider；否则按 Ollama 模型可用性自动选。
    离线档统一 hash 嵌入 + fake 生成，保证全链路（含 seed）一致。
    """
    forced_embed = settings_env.get("SOLARTRACE_EMBEDDING_PROVIDER", "").lower()
    forced_llm = settings_env.get("SOLARTRACE_LLM_PROVIDER", "").lower()

    if args.online:
        profile, reason = "online", "命令行强制 --online"
    elif args.offline:
        profile, reason = "offline", "命令行强制 --offline"
    elif forced_embed or forced_llm:
        # 用户已显式配置 provider：以 .env 为准，仅照抄，不再判档
        embed = forced_embed or "ollama"
        llm = forced_llm or "ollama"
        extra = {}
        if embed in ("hash", "ollama"):
            extra["SOLARTRACE_EMBEDDING_PROVIDER"] = embed
        if llm in ("fake", "ollama"):
            extra["SOLARTRACE_LLM_PROVIDER"] = llm
        if extra.get("SOLARTRACE_EMBEDDING_PROVIDER") == "hash" or extra.get("SOLARTRACE_LLM_PROVIDER") == "fake":
            profile, reason = "offline", "backend/.env 显式配置 hash/fake"
        else:
            profile, reason = "online", "backend/.env 显式配置 ollama"
        return profile, extra

    models = ollama_models(settings_env)
    embed_model = settings_env.get("SOLARTRACE_EMBEDDING_MODEL", "bge-m3")
    llm_model = settings_env.get("SOLARTRACE_LLM_MODEL", "qwen2.5:7b")
    has_embed = any(m.split(":")[0] == embed_model.split(":")[0] or m.startswith(embed_model) for m in models)
    has_llm = any(m.split(":")[0] == llm_model.split(":")[0] or m.startswith(llm_model) for m in models)

    if has_embed and has_llm:
        profile, reason = "online", f"检测到 Ollama：{embed_model} + {llm_model}"
    else:
        profile, reason = (
            "offline",
            "未检测到可用 Ollama 模型 → 离线档（hash 嵌入 + fake 生成，检索链路仍可跑通）",
        )
    return profile, ({}
                    if profile == "online"
                    else {"SOLARTRACE_EMBEDDING_PROVIDER": "hash", "SOLARTRACE_LLM_PROVIDER": "fake"})


# --------------------------------------------------------------------------- #
# 2) 依赖就绪（只发生在仓库内部 venv / node_modules，不碰本机全局）
# --------------------------------------------------------------------------- #
def ensure_backend_env() -> Path:
    py = venv_python()
    if py.exists():
        # 轻量自检：后端是否真的装好了（导入 app 依赖最廉价的关键包）
        try:
            subprocess.run(
                [str(py), "-c", "import fastapi, sqlalchemy, chromadb"],
                cwd=BACKEND, capture_output=True, check=True,
            )
            log(f"后端 venv 就绪：{py.relative_to(ROOT)}")
            return py
        except subprocess.CalledProcessError:
            warn("backend/.venv 存在但依赖不完整，将用 uv 重新同步")
    else:
        log("首次运行：使用 uv 创建 backend/.venv 并安装依赖（仅装进仓库内，不污染本机）")

    uv = shutil.which("uv")
    if uv is None:
        sys.exit("[start] 找不到 uv。请先安装 https://astral.sh/uv （或用 `uv` 运行本脚本），"
                 "再重试。后端将严格在 uv 管理的 backend/.venv 中运行。")
    subprocess.run([uv, "sync", "--extra", "test"], cwd=BACKEND, check=True)
    if not py.exists():
        sys.exit("[start] uv sync 后仍未生成 backend/.venv，请检查 backend/uv.lock 与网络（镜像源）。")
    log(f"后端依赖已装好（backend/.venv）")
    return py


def ensure_frontend_deps() -> None:
    if (FRONTEND / "node_modules").exists():
        log("前端 node_modules 已存在，直接复用")
        return
    if shutil.which("npm") is None:
        sys.exit("[start] 缺少 node_modules 且找不到 npm，无法安装前端依赖。"
                 "请先在 frontend/ 下手动 `npm install`（装进项目内）。")
    log("首次运行：在 frontend/node_modules 安装前端依赖（仅装进项目内）")
    subprocess.run(["npm", "install", "--no-audit", "--no-fund"], cwd=FRONTEND, check=True)


# --------------------------------------------------------------------------- #
# 3) 语料灌入（幂等）
# --------------------------------------------------------------------------- #
def need_seed(profile: str, args: argparse.Namespace) -> bool:
    if args.seed:
        return True
    if args.no_seed:
        return False
    db_missing = not (DATA_DIR / "solartrace.db").exists()
    chroma_missing = not (DATA_DIR / "chroma").exists()
    if db_missing or chroma_missing:
        log("检测到空数据目录，启动前先灌入演示语料")
        return True
    if SEED_MARKER.exists() and SEED_MARKER.read_text(encoding="utf-8").strip() == profile:
        return False
    warn(f"检测到数据目录由另一 provider 档位生成（期望 {profile}），将幂等重建演示索引")
    return True


def run_seed(py: Path, extra_env: dict[str, str]) -> None:
    env = {**os.environ, **extra_env}
    log("灌入演示语料与评测集（幂等）…")
    subprocess.run([str(py), "-m", "app.scripts.seed_demo"], cwd=BACKEND, env=env, check=True)


# --------------------------------------------------------------------------- #
# 4) 端口工具
# --------------------------------------------------------------------------- #
def port_free(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) != 0


def wait_http(url: str, timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as r:  # noqa: S310
                if r.status == 200:
                    return True
        except urllib.error.HTTPError as e:
            if e.code == 404:  # 服务已起来但路由未命中也算活了
                return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


# --------------------------------------------------------------------------- #
# 5) 进程管理
# --------------------------------------------------------------------------- #
class Launcher:
    def __init__(self) -> None:
        self.procs: list[subprocess.Popen] = []

    def start(self, argv: list[str], cwd: Path, env: dict[str, str]) -> None:
        kwargs: dict = {"cwd": cwd, "env": env}
        if SYSTEM_IS_WIN:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        log("启动: " + " ".join(str(a) for a in argv))
        self.procs.append(subprocess.Popen(argv, **kwargs))  # noqa: S603

    def shutdown(self) -> None:
        log("正在回收子进程…")
        for p in self.procs:
            if p.poll() is not None:
                continue
            try:
                if SYSTEM_IS_WIN:
                    subprocess.run(["taskkill", "/pid", str(p.pid), "/t", "/f"],
                                   capture_output=True)  # noqa: S603
                else:
                    p.send_signal(signal.SIGTERM)
            except Exception:  # noqa: BLE001
                pass
        for p in self.procs:
            try:
                p.wait(timeout=5)
            except Exception:  # noqa: BLE001
                pass
        self.procs.clear()


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="SolarTrace 一键启动前后端（uv 管理 venv，不污染本机）")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="强制离线档（hash 嵌入 + fake 生成）")
    mode.add_argument("--online", action="store_true", help="强制在线档（本机 Ollama）")
    ap.add_argument("--seed", action="store_true", help="强制（幂等）重灌演示语料")
    ap.add_argument("--no-seed", action="store_true", help="不灌语料，直接起服务")
    ap.add_argument("--no-frontend", action="store_true", help="只起后端")
    ap.add_argument("--no-check", action="store_true", help="端口被占用时不提示直接覆盖")
    ap.add_argument("--backend-port", type=int, default=BACKEND_PORT)
    ap.add_argument("--frontend-port", type=int, default=FRONTEND_PORT)
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    if args.offline and args.online:
        sys.exit("[start] --offline 与 --online 不能同时使用")

    if not (BACKEND / "app").is_dir() or not (FRONTEND / "package.json").exists():
        sys.exit("[start] 请在仓库根目录运行：python start.py")

    # 0) 读用户自定义 backend/.env（缺失则从示例复制）
    env_file = BACKEND / ".env"
    if not env_file.exists():
        shutil.copy(BACKEND / ".env.example", env_file)
        log("backend/.env 不存在，已从 .env.example 复制（可自行修改密钥/模型）")
    settings_env = _read_env_file(env_file)

    # 1) 依赖就绪（仓库内 venv / node_modules）
    py = ensure_backend_env()
    if not args.no_frontend:
        ensure_frontend_deps()

    # 2) 运行档位（online / offline）与 seed
    profile, extra_env = choose_profile(args, settings_env)
    log(f"运行档位：{profile}  {extra_env or ''}")
    if need_seed(profile, args):
        run_seed(py, extra_env)
        SEED_MARKER.parent.mkdir(parents=True, exist_ok=True)
        SEED_MARKER.write_text(profile + "\n", encoding="utf-8")
    else:
        log("演示语料已就绪，跳过灌入（如需重建加 --seed）")

    # 3) 端口占用提示
    for name, port in (("后端", args.backend_port), ("前端", args.frontend_port)):
        if not port_free(port) and not args.no_check:
            print(f"[start] 端口 {port} 已被占用（{name}）。可换端口："
                  f"--backend-port / --frontend-port，或用 --no-check 继续。", file=sys.stderr)
            return 1

    # 4) 起后端 / 前端
    launcher = Launcher()
    backend_env = {**os.environ, **extra_env, "SOLARTRACE_CORS_ORIGINS": ",".join([
        f"http://localhost:{args.frontend_port}", f"http://127.0.0.1:{args.frontend_port}",
    ])}
    launcher.start(
        [str(py), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
         "--port", str(args.backend_port)],
        cwd=BACKEND, env=backend_env,
    )

    if not args.no_frontend:
        front_env = {**os.environ, "VITE_API_TARGET": f"http://127.0.0.1:{args.backend_port}"}
        launcher.start(
            [shutil.which("npm") or "npm", "run", "dev", "--", "--port", str(args.frontend_port)],
            cwd=FRONTEND, env=front_env,
        )

    # 5) 等待就绪并打印访问信息
    try:
        backend_ok = wait_http(f"http://127.0.0.1:{args.backend_port}/api/v1/system/health")
        print()
        print("=" * 64)
        print("  SolarTrace（光溯）已启动")
        print(f"    前端   http://localhost:{args.frontend_port}  （admin / admin123）")
        print(f"    后端   http://127.0.0.1:{args.backend_port}   （OpenAPI 文档 /docs）")
        print(f"    健康   http://127.0.0.1:{args.backend_port}/api/v1/system/health"
              f"  →  {'OK' if backend_ok else '尚未就绪（请稍候或看后端日志）'}")
        print("  按 Ctrl+C 退出（同时回收前后端进程）")
        print("=" * 64)
        # 若前端也起了，等它 ready（Vite 启动快）
        if not args.no_frontend:
            wait_http(f"http://127.0.0.1:{args.frontend_port}/", timeout=30)
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print()
        log("收到退出信号")
    finally:
        launcher.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

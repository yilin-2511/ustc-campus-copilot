"""
校园 Copilot 一键环境初始化
===========================
用法: python scripts/setup.py

自动完成:
1. 安装 Python 依赖 (pip install -r requirements.txt)
2. 下载 m3e-base 嵌入模型 (从 ModelScope)
3. 构建 ChromaDB 向量库 (从 n7_qa_knowledge.json)
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models" / "xrunda" / "m3e-base"


def step(title: str):
    print(f"\n{'=' * 55}")
    print(f"  {title}")
    print("=" * 55)


def check_python():
    """检查 Python 版本"""
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 10):
        print(f"❌ Python 版本过低: {v.major}.{v.minor}，需要 3.10+")
        sys.exit(1)
    print(f"✅ Python {v.major}.{v.minor}.{v.micro}")


def install_deps():
    """安装依赖"""
    req_file = ROOT / "requirements.txt"
    if not req_file.exists():
        print("⚠️  requirements.txt 不存在，跳过")
        return
    print("⏳ 安装 Python 依赖...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r", str(req_file)]
    )
    print("✅ 依赖安装完成")


def download_model():
    """下载 m3e-base 模型"""
    if MODELS_DIR.exists() and (MODELS_DIR / "pytorch_model.bin").exists():
        print(f"✅ 模型已存在: {MODELS_DIR}")
        return

    print("⏳ 从 ModelScope 下载 m3e-base 模型...")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        from modelscope import snapshot_download

        snapshot_download("xrunda/m3e-base", cache_dir=str(MODELS_DIR.parent))
        print("✅ 模型下载完成")
    except ImportError:
        print("⚠️  modelscope 未安装，尝试 pip install modelscope...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "modelscope"]
        )
        from modelscope import snapshot_download

        snapshot_download("xrunda/m3e-base", cache_dir=str(MODELS_DIR.parent))
        print("✅ 模型下载完成")
    except Exception as e:
        print(f"⚠️  ModelScope 下载失败: {e}")
        print("   将使用 HuggingFace 自动下载（首次运行时会自动拉取）")


def build_kb():
    """构建 ChromaDB 向量库"""
    kb_file = ROOT / "data" / "raw" / "n7teahouse" / "n7_qa_knowledge.json"
    if not kb_file.exists():
        print(f"❌ 知识库数据不存在: {kb_file}")
        sys.exit(1)

    chroma_dir = ROOT / "chroma_db"
    # Check if already built
    if chroma_dir.exists() and list(chroma_dir.glob("*")):
        print("✅ ChromaDB 已存在，跳过构建")
        print("   如需重建: rm -rf chroma_db && python scripts/build_knowledge_base.py --rebuild")
        return

    print("⏳ 构建 ChromaDB 向量库...")
    sys.path.insert(0, str(ROOT / "scripts"))
    from build_knowledge_base import build_knowledge_base
    build_knowledge_base(rebuild=True, collection_name="campus_knowledge")
    print("✅ ChromaDB 构建完成")


def main():
    print("\n🎓 校园 Copilot — 环境初始化\n")

    check_python()
    install_deps()
    download_model()
    build_kb()

    print(f"""
{'=' * 55}
  ✅ 初始化完成！

  启动 Router Agent:
    Windows PowerShell:
      $env:PYTHONIOENCODING="utf-8"
      python scripts/router_agent.py

    Linux / macOS / Git Bash:
      PYTHONIOENCODING=utf-8 python scripts/router_agent.py

  测试 RAG 检索:
    python scripts/build_knowledge_base.py --query "保研需要什么条件"

  更多文档: README.md
{'=' * 55}
""")


if __name__ == "__main__":
    main()

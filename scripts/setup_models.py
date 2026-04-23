#!/usr/bin/env python
"""
AI-QMS OCR 環境初始化腳本
==========================

git pull 後執行一次，完成：
  1. GPU / CUDA 相容性診斷
  2. 下載所有 EasyOCR 語言模型（32 國語系）
  3. 寫入 sentinel，後續啟動不需重新下載

用法：
    python scripts/setup_models.py              # 標準診斷 + 下載
    python scripts/setup_models.py --fix-gpu    # 偵測到 CUDA 不匹配時自動重裝 PyTorch
    python scripts/setup_models.py --cpu        # 寫入 FORCE_CPU=true，強制 CPU 模式
    python scripts/setup_models.py --reset      # 刪除 sentinel，強制重新下載
"""

import argparse
import sys
from pathlib import Path

# 確保 src 可以 import
sys.path.insert(0, str(Path(__file__).parent.parent))


def _banner(text: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print("=" * 60)


def _step(n: int, total: int, text: str) -> None:
    print(f"\n[Step {n}/{total}] {text}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI-QMS OCR 環境初始化（git pull 後執行一次）"
    )
    parser.add_argument(
        "--fix-gpu",
        action="store_true",
        help="偵測到 CUDA 不匹配時，互動確認後自動重裝 PyTorch",
    )
    parser.add_argument(
        "--cpu",
        action="store_true",
        help="強制 CPU 模式：寫入 FORCE_CPU=true 至 .env",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="刪除 sentinel，強制重新下載所有模型",
    )
    args = parser.parse_args()

    _banner("AI-QMS OCR 環境初始化")
    print("  執行後，後續啟動不需重新下載模型")

    total_steps = 3

    # ── Step 1: GPU 診斷 ──────────────────────────────────────
    _step(1, total_steps, "GPU / CUDA 相容性診斷")

    try:
        from src.ocr.gpu_check import check_gpu
        gpu_result = check_gpu(fix_gpu=args.fix_gpu, force_cpu=args.cpu)

        status_labels = {
            "ok":             "正常",
            "cpu_only":       "CPU 模式（無 CUDA GPU）",
            "no_torch":       "torch 未安裝（OCR 仍可使用 CPU）",
            "cuda_mismatch":  "CUDA 版本不匹配（見上方警告）",
            "unsupported_gpu": "GPU 算力超出 PyTorch stable 支援範圍",
            "cpu_forced":     "已強制 CPU 模式",
        }
        status_label = status_labels.get(gpu_result["status"], gpu_result["status"])
        print(f"  狀態: {status_label}")

        if gpu_result["gpu_name"]:
            print(f"  GPU: {gpu_result['gpu_name']}")
        if gpu_result["torch_cuda"]:
            print(f"  PyTorch CUDA: {gpu_result['torch_cuda']}")
        if gpu_result["driver_cuda"]:
            print(f"  Driver CUDA: {gpu_result['driver_cuda']}")
        if gpu_result["capability"]:
            cap = gpu_result["capability"]
            print(f"  Compute Capability: sm_{cap[0]}{cap[1]}")

    except Exception as e:
        print(f"  [WARN] GPU 診斷例外（非致命）: {e}")

    # ── Step 2: 重置 sentinel（若指定 --reset）────────────────
    _step(2, total_steps, "模型快取檢查")

    try:
        from src.ocr.model_setup import SENTINEL_FILE, EASYOCR_CACHE_DIR

        if args.reset and SENTINEL_FILE.exists():
            SENTINEL_FILE.unlink()
            print("  已刪除 sentinel，將重新下載所有模型")
        elif SENTINEL_FILE.exists() and not args.reset:
            print(f"  模型已就緒（sentinel: {SENTINEL_FILE}）")
            print("  若需強制重新下載，請加 --reset 參數")
    except Exception as e:
        print(f"  [WARN] sentinel 檢查失敗: {e}")

    # ── Step 3: 下載 EasyOCR 模型 ────────────────────────────
    _step(3, total_steps, "下載 EasyOCR 語言模型")

    try:
        import easyocr
    except ImportError:
        print("  [ERROR] EasyOCR 未安裝")
        print("  請先執行：pip install -r requirements.txt")
        sys.exit(1)

    try:
        from src.config import EASYOCR_LANGUAGE_GROUPS
        groups = EASYOCR_LANGUAGE_GROUPS
    except (ImportError, AttributeError):
        groups = [
            ["ch_tra", "ch_sim", "ja", "ko"],
            ["en", "de", "fr", "it", "es", "pt", "nl", "pl", "vi", "id"],
            ["ar", "hi", "th", "ru"],
        ]

    group_names = ["中日韓 (CJK)", "拉丁系", "特殊文字 (阿拉伯/天城文/泰文/西里爾)"]
    failed_groups = []

    from src.ocr.model_setup import SENTINEL_FILE, EASYOCR_CACHE_DIR

    for i, (group, name) in enumerate(zip(groups, group_names), 1):
        print(f"  ({i}/{len(groups)}) {name}")
        print(f"    語言: {group}")
        try:
            easyocr.Reader(group, gpu=False, verbose=False)
            print(f"    ✓ 完成")
        except Exception as e:
            print(f"    ✗ 失敗: {e}")
            failed_groups.append(name)

    # 寫入 sentinel
    try:
        EASYOCR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        SENTINEL_FILE.touch()
    except Exception as e:
        print(f"  [WARN] sentinel 寫入失敗: {e}")

    # ── 摘要 ────────────────────────────────────────────────
    _banner("初始化完成")
    if failed_groups:
        print(f"  部分語系下載失敗：{', '.join(failed_groups)}")
        print("  失敗的語系在使用時會自動重試")
    else:
        print("  所有語言模型下載成功")

    print(f"\n  模型快取位置: {Path.home() / '.EasyOCR' / 'model'}")
    print("  後續啟動 AI-QMS 不需重新下載")
    print("  如需重新下載：python scripts/setup_models.py --reset")

    if not args.cpu and gpu_result.get("status") in ("cuda_mismatch", "unsupported_gpu"):
        print("\n  [提示] GPU 有相容性問題，建議使用 CPU 模式：")
        print("    python scripts/setup_models.py --cpu")


if __name__ == "__main__":
    main()

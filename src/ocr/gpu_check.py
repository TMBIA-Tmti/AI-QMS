"""
GPU / CUDA 相容性診斷模組

偵測 PyTorch CUDA 版本與 GPU driver 的不匹配，
並在不匹配時給出修復建議。

用法：
    from src.ocr.gpu_check import check_gpu
    check_gpu()                   # 啟動時診斷（不阻塞）
    check_gpu(fix_gpu=True)       # 互動式詢問是否重裝 PyTorch
    check_gpu(force_cpu=True)     # 寫入 FORCE_CPU=true 至 .env
"""

import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================================
# 版本偵測
# ============================================================


def _get_driver_cuda_version() -> Optional[str]:
    """從 nvidia-smi 解析 driver 支援的最高 CUDA 版本。"""
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            if "CUDA Version" in line:
                parts = line.split("CUDA Version:")
                if len(parts) > 1:
                    return parts[1].strip().split()[0]
    except FileNotFoundError:
        pass  # nvidia-smi 不存在 → 無 NVIDIA GPU
    except Exception as e:
        logger.debug("nvidia-smi 執行失敗: %s", e)
    return None


def _get_torch_cuda_version() -> Optional[str]:
    """取得 PyTorch 編譯時對應的 CUDA 版本。"""
    try:
        import torch
        return torch.version.cuda  # 可能是 None（CPU-only build）
    except ImportError:
        return None


def _get_gpu_capability() -> Optional[tuple[int, int]]:
    """取得第一張 GPU 的 compute capability (major, minor)。"""
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.get_device_capability(0)
    except Exception as e:
        logger.debug("get_device_capability 失敗: %s", e)
    return None


def _get_gpu_name() -> Optional[str]:
    """取得 GPU 名稱。"""
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
    except Exception:
        pass
    return None


def _recommend_index_url(driver_cuda: str) -> str:
    """根據 driver CUDA 版本推薦 PyTorch wheel index URL。"""
    try:
        major, minor = [int(x) for x in driver_cuda.split(".")[:2]]
        version = major * 10 + minor
    except Exception:
        return "https://download.pytorch.org/whl/cu121"

    if version >= 128:
        return "https://download.pytorch.org/whl/cu128"
    elif version >= 124:
        return "https://download.pytorch.org/whl/cu124"
    elif version >= 121:
        return "https://download.pytorch.org/whl/cu121"
    else:
        return "https://download.pytorch.org/whl/cu118"


# ============================================================
# 主診斷函式
# ============================================================


def check_gpu(fix_gpu: bool = False, force_cpu: bool = False) -> dict:
    """
    執行 GPU / CUDA 相容性診斷。

    Args:
        fix_gpu:   True → 偵測到不匹配時，互動詢問並自動重裝 PyTorch
        force_cpu: True → 寫入 FORCE_CPU=true 至 .env，強制 CPU 模式

    Returns:
        dict:
            status       - "ok" | "cpu_only" | "no_torch" | "cuda_mismatch" | "unsupported_gpu" | "cpu_forced"
            warnings     - list[str]
            torch_cuda   - str | None
            driver_cuda  - str | None
            capability   - (int, int) | None
            gpu_name     - str | None
            recommendation - str | None  (pip 修復指令)
    """
    result: dict = {
        "status": "ok",
        "warnings": [],
        "torch_cuda": None,
        "driver_cuda": None,
        "capability": None,
        "gpu_name": None,
        "recommendation": None,
    }

    # ── 強制 CPU 模式 ──────────────────────────────────────────
    if force_cpu:
        _write_force_cpu()
        result["status"] = "cpu_forced"
        print("[GPU] FORCE_CPU=true 已寫入 .env，所有 ML 引擎將使用 CPU")
        return result

    # ── torch 未安裝 ───────────────────────────────────────────
    torch_cuda = _get_torch_cuda_version()
    if torch_cuda is None:
        result["status"] = "no_torch"
        logger.debug("torch 未安裝，跳過 GPU 診斷")
        return result

    result["torch_cuda"] = torch_cuda

    # ── CPU-only build（torch.version.cuda is None） ──────────
    if torch_cuda == "None" or not torch_cuda:
        result["status"] = "cpu_only"
        logger.info("PyTorch CPU-only build，GPU 加速不可用")
        return result

    # ── 無 CUDA GPU ────────────────────────────────────────────
    capability = _get_gpu_capability()
    result["capability"] = capability
    result["gpu_name"] = _get_gpu_name()

    if capability is None:
        result["status"] = "cpu_only"
        logger.info("未偵測到 CUDA GPU，將使用 CPU 模式")
        return result

    sm_version = capability[0] * 10 + capability[1]

    # ── Blackwell (sm_100+) — PyTorch stable 尚不支援 ─────────
    if sm_version >= 100:
        warn = (
            f"[GPU WARNING] GPU {result['gpu_name']} (sm_{sm_version}) "
            f"超出 PyTorch stable 支援範圍（最高 sm_90）\n"
            f"  RTX 50 系列 (Blackwell) 需要 PyTorch nightly 或使用 CPU 模式\n"
            f"  建議：python scripts/setup_models.py --cpu"
        )
        result["warnings"].append(warn)
        result["status"] = "unsupported_gpu"
        print(warn)

    # ── CUDA 版本不匹配 ────────────────────────────────────────
    driver_cuda = _get_driver_cuda_version()
    result["driver_cuda"] = driver_cuda

    if driver_cuda and torch_cuda:
        try:
            torch_major = int(torch_cuda.split(".")[0])
            driver_major = int(driver_cuda.split(".")[0])
        except ValueError:
            return result

        if abs(torch_major - driver_major) >= 2:
            index_url = _recommend_index_url(driver_cuda)
            pip_cmd = f"pip install torch --index-url {index_url}"
            warn = (
                f"[GPU WARNING] PyTorch CUDA {torch_cuda} ≠ Driver CUDA {driver_cuda}\n"
                f"  建議執行：{pip_cmd}\n"
                f"  或強制 CPU：python scripts/setup_models.py --cpu"
            )
            result["warnings"].append(warn)
            result["recommendation"] = pip_cmd
            result["status"] = "cuda_mismatch"
            print(warn)

            if fix_gpu:
                _do_fix_gpu(pip_cmd)

    return result


# ============================================================
# 輔助操作
# ============================================================


def _do_fix_gpu(pip_cmd: str) -> None:
    """互動式詢問並執行 PyTorch 重裝。"""
    print(f"\n即將執行：{pip_cmd}")
    try:
        ans = input("確認執行？(y/N): ").strip().lower()
    except EOFError:
        ans = "n"

    if ans == "y":
        print("正在重新安裝 PyTorch...")
        try:
            subprocess.check_call(pip_cmd.split())
            print("[OK] PyTorch 重新安裝完成，請重新啟動應用程式")
            sys.exit(0)
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] 重裝失敗: {e}")
    else:
        print("已取消，繼續使用現有 PyTorch")


def _write_force_cpu() -> None:
    """在專案根目錄的 .env 寫入 FORCE_CPU=true。"""
    env_file = Path(".env")

    if env_file.exists():
        content = env_file.read_text(encoding="utf-8")
        if "FORCE_CPU" in content:
            lines = [
                "FORCE_CPU=true" if line.startswith("FORCE_CPU") else line
                for line in content.splitlines()
            ]
            env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return
        with env_file.open("a", encoding="utf-8") as f:
            f.write("\nFORCE_CPU=true\n")
    else:
        env_file.write_text("FORCE_CPU=true\n", encoding="utf-8")


def run_startup_check() -> None:
    """
    應用啟動時呼叫的輕量診斷（不阻塞，只印警告）。
    不支援 --fix-gpu / --cpu，那些只在 setup_models.py 互動模式用。
    """
    try:
        result = check_gpu()
        if result["status"] == "ok" and result["capability"]:
            cap = result["capability"]
            logger.info(
                "GPU 診斷 OK：%s, sm_%d%d, CUDA %s",
                result["gpu_name"], cap[0], cap[1], result["torch_cuda"],
            )
    except Exception as e:
        logger.debug("GPU 啟動診斷例外（非致命）: %s", e)

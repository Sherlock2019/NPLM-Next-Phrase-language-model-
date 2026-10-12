"""Device and dtype selection.

``torch.cuda.is_available()`` is not enough. A CUDA build can be installed and a
GPU present while no kernel for that GPU's compute capability exists - the failure
then surfaces deep inside a parser or a model load as
``cudaErrorNoKernelImageForDevice``. So availability is confirmed by actually
running a tiny kernel once, and the result is cached for the process.

SPLM must run on CPU (spec section 5), so a GPU that does not work is a log line,
never an error.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def cuda_is_usable() -> bool:
    """Whether a CUDA kernel can actually execute on this machine."""
    if os.environ.get("SPLM_FORCE_CPU", "").strip().lower() in {"1", "true", "yes"}:
        logger.info("SPLM_FORCE_CPU is set; using CPU")
        return False
    try:
        import torch
    except ImportError:
        return False

    if not torch.cuda.is_available():
        return False

    try:
        probe = torch.ones(8, 8, device="cuda")
        # Force a real kernel launch and synchronise so errors surface here.
        (probe @ probe).sum().item()
        torch.cuda.synchronize()
        return True
    except Exception as exc:
        name = "unknown"
        try:
            name = torch.cuda.get_device_name(0)
        except Exception:
            pass
        logger.warning(
            "CUDA is present (%s) but unusable, falling back to CPU: %s",
            name,
            str(exc).splitlines()[0],
        )
        return False


def resolve_device(requested: str | bool | None = "auto") -> str:
    """Turn a configured device setting into a concrete torch device string."""
    if requested is True:
        requested = "cuda"
    elif requested is False:
        requested = "cpu"

    value = str(requested or "auto").strip().lower()

    if value in {"auto", ""}:
        return "cuda" if cuda_is_usable() else "cpu"
    if value.startswith("cuda"):
        if cuda_is_usable():
            return value
        logger.warning("device %r requested but CUDA is unusable; using CPU", value)
        return "cpu"
    return value


def resolve_use_gpu(requested: str | bool | None = "auto") -> bool:
    """Boolean form, for libraries that take ``use_gpu=`` rather than a device."""
    return resolve_device(requested).startswith("cuda")


def resolve_dtype(requested: str | None, device: str) -> Any | None:
    """Pick a torch dtype.

    ``auto`` means float32 on CPU (float16 there is slow and often unsupported) and
    on GPU float16, upgraded to bfloat16 only when the hardware really supports it.
    """
    try:
        import torch
    except ImportError:
        return None

    value = (requested or "auto").strip().lower()
    named = {
        "float32": torch.float32,
        "fp32": torch.float32,
        "float16": torch.float16,
        "fp16": torch.float16,
        "half": torch.float16,
        "bfloat16": torch.bfloat16,
        "bf16": torch.bfloat16,
    }
    if value in named:
        return named[value]
    if value not in {"auto", ""}:
        logger.warning("unknown dtype %r; using auto", requested)

    if not device.startswith("cuda"):
        return torch.float32
    try:
        if torch.cuda.is_bf16_supported():
            return torch.bfloat16
    except Exception:
        pass
    return torch.float16


def device_report() -> dict[str, Any]:
    """Human-readable summary of what SPLM will run on, for benchmark metadata."""
    report: dict[str, Any] = {"cuda_usable": cuda_is_usable(), "device": resolve_device("auto")}
    try:
        import torch

        report["torch"] = torch.__version__
        report["cuda_available"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            report["gpu_name"] = torch.cuda.get_device_name(0)
            major, minor = torch.cuda.get_device_capability(0)
            report["compute_capability"] = f"{major}.{minor}"
    except Exception:
        report["torch"] = None
    return report

#!/usr/bin/env python3
"""
scripts/download_model.py
--------------------------
Downloads GGUF model weights from HuggingFace into the local /models directory.

Uses huggingface-hub for reliable resumable downloads with progress display.

Usage
-----
    python scripts/download_model.py                    # Phi-3 Mini (default)
    python scripts/download_model.py --model fallback   # Qwen2.5 1.5B
    python scripts/download_model.py --model gemma      # Gemma-2 2B
    python scripts/download_model.py --list             # Show all options
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from huggingface_hub import hf_hub_download
except ImportError:
    print(
        "\n[ERROR] huggingface-hub is not installed.\n"
        "  Run:  pip install huggingface-hub\n"
        "  Or:   pip install -e '.[dev]'  (installs all dependencies)\n",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

MODELS: dict[str, dict] = {
    "default": {
        "repo_id":     "microsoft/Phi-3-mini-4k-instruct-gguf",
        "filename":    "Phi-3-mini-4k-instruct-q4.gguf",
        "description": "Phi-3 Mini 3.8B (Q4, ~2.3 GB) -- recommended default",
        "min_ram_gb":  4,
    },
    "fallback": {
        "repo_id":     "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
        "filename":    "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "description": "Qwen2.5 1.5B (Q4_K_M, ~1.0 GB) -- for 4 GB RAM machines",
        "min_ram_gb":  2,
    },
    "gemma": {
        "repo_id":     "bartowski/gemma-2-2b-it-GGUF",
        "filename":    "gemma-2-2b-it-Q4_K_M.gguf",
        "description": "Gemma 2 2B (Q4_K_M, ~1.2 GB) -- alternative fallback",
        "min_ram_gb":  3,
    },
}

MODELS_DIR = Path(os.getenv("SCHOLAROS_MODELS_DIR", "models"))


# ---------------------------------------------------------------------------
# Core download function
# ---------------------------------------------------------------------------

def download_model(model_key: str = "default") -> Path:
    if model_key not in MODELS:
        valid = ", ".join(MODELS.keys())
        raise ValueError(f"Unknown model '{model_key}'. Choose from: {valid}")

    spec = MODELS[model_key]
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    dest = MODELS_DIR / spec["filename"]

    if dest.exists():
        size_mb = dest.stat().st_size / 1_048_576
        print(f"[OK] Model already present: {dest}  ({size_mb:.1f} MB)")
        return dest

    print(f"\nDownloading : {spec['description']}")
    print(f"  Repo      : {spec['repo_id']}")
    print(f"  File      : {spec['filename']}")
    print(f"  Into      : {MODELS_DIR.resolve()}")
    print(f"  Min RAM   : {spec['min_ram_gb']} GB")
    print()

    try:
        # NOTE: local_dir_use_symlinks removed in huggingface-hub >= 0.23.0 -- do NOT pass it.
        hf_hub_download(
            repo_id=spec["repo_id"],
            filename=spec["filename"],
            local_dir=str(MODELS_DIR),
        )
    except KeyboardInterrupt:
        print("\n[CANCELLED] Download interrupted. Partial file kept for resumption.")
        sys.exit(1)
    except Exception as exc:
        print(f"\n[ERROR] Download failed: {exc}", file=sys.stderr)
        print(
            "  Tip: check your internet connection and re-run.\n"
            "  Partial downloads are resumed automatically.\n",
            file=sys.stderr,
        )
        sys.exit(1)

    size_mb = dest.stat().st_size / 1_048_576
    print(f"[OK] Saved to {dest}  ({size_mb:.1f} MB)")
    return dest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="download_model.py",
        description="Download ScholarOS GGUF model weights from HuggingFace.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Available models:\n" + "\n".join(
            f"  {k:10s}  {v['description']}" for k, v in MODELS.items()
        ),
    )
    parser.add_argument(
        "--model",
        default="default",
        choices=list(MODELS.keys()),
        metavar="MODEL",
        help="Which model to download (default: %(default)s). Choices: " + ", ".join(MODELS.keys()),
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available models with download status, then exit.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.list:
        print("\nAvailable models:\n")
        for key, spec in MODELS.items():
            path = MODELS_DIR / spec["filename"]
            if path.exists():
                size_mb = path.stat().st_size / 1_048_576
                status = f"downloaded  ({size_mb:.1f} MB)"
            else:
                status = "not downloaded"
            print(f"  {key:10s}  {spec['description']:50s}  [{status}]")
        print()
        return

    download_model(args.model)


if __name__ == "__main__":
    main()
"""
core/llm_client.py
------------------
In-process LLM inference for ScholarOS using llama-cpp-python.

No external servers. No cloud APIs. The model weights live in /models
and are loaded once at startup, then reused for every request.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator, Optional

try:
    from llama_cpp import Llama
except ImportError:
    raise ImportError(
        "llama-cpp-python not installed.\n"
        "  • Linux/Mac:  pip install llama-cpp-python\n"
        "  • Windows:    see scripts/setup.bat for pre-compiled wheel instructions"
    )

# ---------------------------------------------------------------------------
# Constants / defaults
# ---------------------------------------------------------------------------

MODELS_DIR = Path(os.getenv("SCHOLAROS_MODELS_DIR", "models"))

# Default model — Phi-3 Mini 3.8B (GGUF, 4-bit quantised, ~2.2 GB)
DEFAULT_MODEL_FILENAME = os.getenv(
    "SCHOLAROS_MODEL_FILE", "Phi-3-mini-4k-instruct-q4.gguf"
)

# Fallback for machines with strict 4 GB RAM budgets
FALLBACK_MODEL_FILENAME = "qwen2.5-1.5b-instruct-q4_k_m.gguf"

# Generation defaults
DEFAULT_MAX_TOKENS = 512
DEFAULT_TEMPERATURE = 0.2      # Low temp → factual, consistent answers
DEFAULT_CONTEXT_LENGTH = 4096  # Must match the model's context window

# ---------------------------------------------------------------------------
# LLMClient
# ---------------------------------------------------------------------------

class LLMClient:
    """
    Manages a single llama.cpp model loaded in-process.
    The model is loaded lazily on the first call to ``generate``.
    """

    def __init__(
        self,
        model_filename: Optional[str] = None,
        models_dir: str | Path = MODELS_DIR,
        n_ctx: int = DEFAULT_CONTEXT_LENGTH,
        n_threads: Optional[int] = None,
        verbose: bool = False,
    ) -> None:
        self._models_dir = Path(models_dir)
        self._model_filename = model_filename or DEFAULT_MODEL_FILENAME
        self._n_ctx = n_ctx
        self._n_threads = n_threads  # None → llama.cpp auto-detects
        self._verbose = verbose
        self._llm: Optional[Llama] = None  # loaded lazily

    # ------------------------------------------------------------------
    # Lazy loading
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load model weights into memory (called once)."""
        model_path = self._models_dir / self._model_filename

        if not model_path.exists():
            # Try fallback automatically
            fallback_path = self._models_dir / FALLBACK_MODEL_FILENAME
            if fallback_path.exists():
                print(
                    f"[LLMClient] Primary model not found. "
                    f"Falling back to '{FALLBACK_MODEL_FILENAME}'."
                )
                model_path = fallback_path
            else:
                raise FileNotFoundError(
                    f"No model found in '{self._models_dir}'.\n"
                    f"Run:  make fetch-model\n"
                    f"  or: python scripts/download_model.py"
                )

        print(f"[LLMClient] Loading model from '{model_path}' …")
        self._llm = Llama(
            model_path=str(model_path),
            n_ctx=self._n_ctx,
            n_threads=self._n_threads,
            verbose=self._verbose,
        )
        print("[LLMClient] Model loaded and ready.")

    @property
    def llm(self) -> Llama:
        if self._llm is None:
            self._load()
        return self._llm

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        stop: Optional[list[str]] = None,
    ) -> str:
        """Generate a completion for *prompt* and return the full text."""
        response = self.llm(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop or ["</s>", "<|end|>", "<|im_end|>"],
            echo=False,
        )
        return response["choices"][0]["text"].strip()

    def generate_stream(
        self,
        prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        stop: Optional[list[str]] = None,
    ) -> Iterator[str]:
        """Stream tokens one-by-one as they are generated."""
        stream = self.llm(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop or ["</s>", "<|end|>", "<|im_end|>"],
            stream=True,
            echo=False,
        )
        for chunk in stream:
            token = chunk["choices"][0]["text"]
            if token:
                yield token

    # ------------------------------------------------------------------
    # Prompt helpers
    # ------------------------------------------------------------------

    @staticmethod
    def build_rag_prompt(
        system_prompt: str,
        context_chunks: list[str],
        user_question: str,
    ) -> str:
        """
        Assemble a RAG prompt from retrieved context chunks.
        """
        context_block = "\n\n---\n\n".join(context_chunks)

        return (
            f"<|system|>\n{system_prompt}<|end|>\n"
            f"<|user|>\n"
            f"Use only the context below to answer the question. "
            f"If the answer is not in the context, say so clearly.\n\n"
            f"### Context\n{context_block}\n\n"
            f"### Question\n{user_question}<|end|>\n"
            f"<|assistant|>\n"
        )
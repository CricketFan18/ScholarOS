"""
core/llm_client.py
------------------
In-process LLM inference for ScholarOS using llama-cpp-python.

No external servers. No cloud APIs. Model weights live in /models and are
loaded once at startup via lazy initialisation, then reused for every request.

Supported model formats: GGUF (quantised), compatible with Phi-3, Qwen2.5,
Mistral, Llama 3, and most other llama.cpp-supported architectures.

Quick start:

    from core.llm_client import LLMClient
    client = LLMClient()
    print(client.generate("Explain gradient descent in one sentence."))
"""

from __future__ import annotations

import os
import threading
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

# Environment variables allow operators to swap models without changing code.
DEFAULT_MODEL_FILENAME  = os.getenv("SCHOLAROS_MODEL_FILE", "Phi-3-mini-4k-instruct-q4.gguf")
FALLBACK_MODEL_FILENAME = "qwen2.5-1.5b-instruct-q4_k_m.gguf"  # ~1 GB — fits in 4 GB RAM

DEFAULT_MAX_TOKENS     = 512
DEFAULT_TEMPERATURE    = 0.2   # low temperature → more factual, less creative
DEFAULT_CONTEXT_LENGTH = 4096  # tokens; must match the model's native context window


# ---------------------------------------------------------------------------
# LLMClient
# ---------------------------------------------------------------------------

class LLMClient:
    """
    Manages a single llama.cpp model loaded in-process.

    Design decisions:
    - **Lazy loading**: The model is not loaded at construction time. The first
      call to `.generate()` or `.generate_stream()` triggers `_load()`. This
      lets the FastAPI app start and pass health checks before the (slow) model
      load completes.
    - **Thread safety**: A `threading.Lock` ensures `_load()` is called at most
      once, even when multiple async requests arrive simultaneously during cold
      start. We use double-checked locking to avoid acquiring the lock on every
      request after the model is loaded.
    - **Fallback model**: If the configured model file is missing, the client
      automatically tries a smaller fallback model so development machines with
      limited RAM can still run the application.
    """

    def __init__(
        self,
        model_filename: Optional[str] = None,
        models_dir: str | Path = MODELS_DIR,
        n_ctx: int = DEFAULT_CONTEXT_LENGTH,
        n_threads: Optional[int] = None,
        verbose: bool = False,
    ) -> None:
        """
        Args:
            model_filename: GGUF filename inside `models_dir`. Defaults to the
                            environment variable SCHOLAROS_MODEL_FILE.
            models_dir:     Directory containing model weight files.
            n_ctx:          Context window length in tokens.
            n_threads:      CPU threads for inference. None → llama.cpp auto-detects.
            verbose:        If True, llama.cpp prints internal debug output.
        """
        self._models_dir     = Path(models_dir)
        self._model_filename = model_filename or DEFAULT_MODEL_FILENAME
        self._n_ctx          = n_ctx
        self._n_threads      = n_threads
        self._verbose        = verbose
        self._llm: Optional[Llama] = None
        self._load_lock      = threading.Lock()   # guards lazy initialisation

    # ------------------------------------------------------------------
    # Lazy loading — thread-safe
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """
        Load model weights into memory. Called at most once (guarded by `_load_lock`).

        Falls back to FALLBACK_MODEL_FILENAME if the primary model is absent,
        which is useful for CI environments or low-RAM development machines.
        """
        model_path = self._models_dir / self._model_filename

        if not model_path.exists():
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
        """
        Return the loaded Llama instance, initialising it on first access.

        Uses double-checked locking:
          1. Check `_llm is None` without the lock (fast path for loaded model).
          2. Acquire the lock and check again (prevents duplicate loading if two
             threads race during the very first request).
        """
        if self._llm is None:
            with self._load_lock:
                if self._llm is None:   # second check inside the lock
                    self._load()
        return self._llm  # type: ignore[return-value]

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
        """
        Generate a completion for `prompt` and return the full response as a string.

        Use this for non-streaming tasks (flashcards, summaries) where the entire
        response must be available before it can be processed or returned.

        Args:
            prompt:      The fully assembled prompt string (use `build_rag_prompt`).
            max_tokens:  Maximum tokens to generate.
            temperature: Sampling temperature. Lower → more deterministic.
            stop:        List of stop sequences. Defaults to common EOS tokens.

        Returns:
            The generated text, stripped of leading/trailing whitespace.
        """
        response = self.llm(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop or ["</s>", "<|end|>", "<|im_end|>"],
            echo=False,   # don't include the prompt in the output
        )
        return response["choices"][0]["text"].strip()

    def generate_stream(
        self,
        prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        stop: Optional[list[str]] = None,
    ) -> Iterator[str]:
        """
        Stream tokens one-by-one as they are generated.

        Use this for Q&A responses where low time-to-first-token matters.
        Empty tokens (which llama.cpp occasionally emits) are filtered out
        to avoid sending unnecessary SSE events to the client.

        Args:
            prompt:      The fully assembled prompt string.
            max_tokens:  Maximum tokens to generate.
            temperature: Sampling temperature.
            stop:        List of stop sequences.

        Yields:
            Individual text tokens as strings.
        """
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
            if token:   # skip empty tokens that llama.cpp occasionally emits
                yield token

    # ------------------------------------------------------------------
    # Prompt assembly
    # ------------------------------------------------------------------

    @staticmethod
    def build_rag_prompt(
        system_prompt: str,
        context_chunks: list[str],
        user_question: str,
        history: Optional[list[dict]] = None,
    ) -> str:
        """
        Assemble a complete RAG prompt using the Phi-3 / ChatML chat template.

        The prompt structure is:
          <|system|> ... <|end|>
          [optional prior turns]
          <|user|>
          ### Context
          [retrieved passages]
          ### Question
          [user question]
          <|end|>
          <|assistant|>

        Injecting context into the user turn (rather than the system turn) has
        been empirically found to produce better grounding on small models, as
        they tend to prioritise the most recent content in their context window.

        Args:
            system_prompt:  Persona and task instructions for the mode.
            context_chunks: Retrieved document passages from the vector store.
            user_question:  The student's current question.
            history:        Optional list of prior conversation turns, each a
                            dict with keys "role" ("user" | "assistant") and
                            "content". Most recent turn last.

        Returns:
            A fully formatted prompt string ready to pass to `generate` or
            `generate_stream`.
        """
        context_block = "\n\n---\n\n".join(context_chunks)

        # Build the history block from prior conversation turns, if provided.
        # Each turn is wrapped in the model's native chat tags so the model
        # understands the role of each message.
        history_block = ""
        if history:
            turns = []
            for turn in history:
                role    = turn.get("role", "user")
                content = turn.get("content", "").strip()
                if content:
                    tag = "<|user|>" if role == "user" else "<|assistant|>"
                    turns.append(f"{tag}\n{content}<|end|>")
            if turns:
                history_block = "\n".join(turns) + "\n"

        return (
            f"<|system|>\n{system_prompt}<|end|>\n"
            f"{history_block}"
            f"<|user|>\n"
            f"Use only the context below to answer the question. "
            f"If the answer is not in the context, say so clearly.\n\n"
            f"### Context\n{context_block}\n\n"
            f"### Question\n{user_question}<|end|>\n"
            f"<|assistant|>\n"
        )
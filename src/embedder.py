"""Embedding 统一接口：支持本地 ONNX 和云端 API"""

import os
from pathlib import Path
import re
import time
from typing import Protocol
import numpy as np

from src.config import EmbeddingConfig


class EmbedderProtocol(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class EmbeddingRequestError(RuntimeError):
    """Non-retryable embedding request error."""


class EmbeddingInputError(EmbeddingRequestError):
    """Embedding request failed for a single input."""


def embedding_batch_size(config: EmbeddingConfig) -> int:
    if config.batch_size and config.batch_size > 0:
        return config.batch_size
    if config.provider == "glm":
        return 16
    return 64


def resolve_api_key_with_source(
    config: EmbeddingConfig,
    default_env: str = "",
    ignore_file_errors: bool = False,
) -> tuple[str, str]:
    if config.api_key:
        return config.api_key, "inline"
    if config.api_key_file:
        key_path = Path(config.api_key_file).expanduser()
        try:
            value = key_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            if ignore_file_errors:
                return "", "file"
            raise ValueError(f"embedding api_key_file 无法读取: {key_path}") from exc
        if value:
            return value, "file"
        if ignore_file_errors:
            return "", "file"
        raise ValueError(f"embedding api_key_file 为空: {key_path}")
    env_name = config.api_key_env or default_env
    if env_name:
        value = os.environ.get(env_name, "")
        if value:
            return value, f"env:{env_name}"
    return "", ""


def resolve_api_key(config: EmbeddingConfig, default_env: str = "") -> str:
    return resolve_api_key_with_source(config, default_env)[0]


class ONNXEmbedder:
    """本地 ONNX Runtime embedding"""

    def __init__(self, model_name: str, model_dir: str):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.model_dir = Path(model_dir)
        model_path = self.model_dir / model_name / "model.onnx"
        tokenizer_path = self.model_dir / model_name / "tokenizer.json"

        if not model_path.exists():
            raise FileNotFoundError(
                f"ONNX 模型未找到: {model_path}\n"
                f"请先下载模型到 {self.model_dir / model_name}/ 目录"
            )

        self.session = ort.InferenceSession(str(model_path))
        self.tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self.tokenizer.enable_padding(length=128)
        self.tokenizer.enable_truncation(max_length=128)

    def embed(self, texts: list[str]) -> list[list[float]]:
        encodings = self.tokenizer.encode_batch(texts)

        input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
        token_type_ids = np.zeros_like(input_ids)

        inputs = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        }

        # 只传模型实际需要的输入
        model_inputs = {i.name for i in self.session.get_inputs()}
        inputs = {k: v for k, v in inputs.items() if k in model_inputs}

        outputs = self.session.run(None, inputs)
        embeddings = self._mean_pool(outputs[0], attention_mask)
        return embeddings.tolist()

    def _mean_pool(self, token_embeddings: np.ndarray, attention_mask: np.ndarray) -> np.ndarray:
        mask_expanded = np.expand_dims(attention_mask, -1).astype(np.float32)
        sum_embeddings = np.sum(token_embeddings * mask_expanded, axis=1)
        sum_mask = np.clip(mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
        return sum_embeddings / sum_mask


class HTTPEmbeddingClient:
    """OpenAI-compatible HTTP embedding client."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        dimensions: int | None = None,
        timeout: float = 60.0,
        max_retries: int = 3,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.dimensions = dimensions
        self.timeout = timeout
        self.max_retries = max(1, max_retries)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        texts = [self._sanitize_text(text) for text in texts]
        try:
            return self._embed_once(texts)
        except EmbeddingInputError:
            raise
        except EmbeddingRequestError:
            if len(texts) <= 1:
                raise
            mid = len(texts) // 2
            return self.embed(texts[:mid]) + self.embed(texts[mid:])
        except Exception:
            if len(texts) <= 1:
                raise
            mid = len(texts) // 2
            return self.embed(texts[:mid]) + self.embed(texts[mid:])

    def _embed_once(self, texts: list[str]) -> list[list[float]]:
        import httpx

        payload = {
            "model": self.model,
            "input": texts,
        }
        if self.dimensions is not None:
            payload["dimensions"] = self.dimensions

        last_exc = None
        for attempt in range(self.max_retries):
            try:
                response = httpx.post(
                    f"{self.base_url}/embeddings",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                break
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if 400 <= exc.response.status_code < 500:
                    raise self._status_error(exc, texts) from exc
                if attempt == self.max_retries - 1:
                    raise self._status_error(exc, texts) from exc
                time.sleep(0.8 * (attempt + 1))
            except (
                httpx.RemoteProtocolError,
                httpx.ReadError,
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.NetworkError,
            ) as exc:
                last_exc = exc
                if attempt == self.max_retries - 1:
                    raise RuntimeError(
                        "embedding request failed after "
                        f"{self.max_retries} attempts: {type(exc).__name__}: {exc}"
                    ) from exc
                time.sleep(0.8 * (attempt + 1))
        else:
            raise RuntimeError(f"embedding request failed: {last_exc}") from last_exc

        data = response.json()
        items = sorted(data.get("data", []), key=lambda item: item.get("index", 0))
        if len(items) != len(texts):
            raise RuntimeError(
                f"embedding response count mismatch: expected {len(texts)}, got {len(items)}"
            )
        return [item["embedding"] for item in items]

    def _status_error(self, exc, texts: list[str]) -> EmbeddingRequestError:
        body = exc.response.text[:1000]
        longest = max(len(text) for text in texts) if texts else 0
        error_cls = EmbeddingInputError if len(texts) <= 1 else EmbeddingRequestError
        preview = ""
        if len(texts) <= 1 and texts:
            preview = f" preview={texts[0][:240]!r}"
        return error_cls(
            f"embedding HTTP {exc.response.status_code} for {len(texts)} inputs "
            f"(longest_chars={longest}){preview}: {body}"
        )

    def _sanitize_text(self, text: str) -> str:
        text = "" if text is None else str(text)
        text = text.replace("\x00", " ")
        text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text or " "


class OpenAIEmbedder(HTTPEmbeddingClient):
    """OpenAI API embedding."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        super().__init__(
            api_key=api_key,
            model=model,
            base_url="https://api.openai.com/v1",
        )


class OpenAICompatibleEmbedder(HTTPEmbeddingClient):
    """Embedding client for OpenAI-compatible providers such as GLM."""


def create_embedder(config: EmbeddingConfig) -> EmbedderProtocol:
    if config.provider == "local":
        return ONNXEmbedder(config.local_model, config.model_dir)
    elif config.provider == "openai":
        api_key = config.openai_api_key or resolve_api_key(config, "OPENAI_API_KEY")
        model = config.openai_model if not config.model else config.model
        if not api_key:
            raise ValueError("openai_api_key 未配置")
        return OpenAIEmbedder(api_key, model)
    elif config.provider in ("openai_compatible", "glm"):
        api_key = resolve_api_key(config)
        if config.provider == "glm":
            api_key = api_key or os.environ.get("ZHIPU_API_KEY", "")
            base_url = config.base_url or "https://open.bigmodel.cn/api/paas/v4"
            model = config.model or "embedding-3"
        else:
            base_url = config.base_url
            model = config.model
        if not api_key:
            env_hint = config.api_key_env or ("ZHIPU_API_KEY" if config.provider == "glm" else "")
            suffix = f" 或环境变量 {env_hint}" if env_hint else ""
            raise ValueError(f"embedding api_key 未配置{suffix}")
        if not base_url:
            raise ValueError("embedding base_url 未配置")
        if not model:
            raise ValueError("embedding model 未配置")
        return OpenAICompatibleEmbedder(
            api_key=api_key,
            model=model,
            base_url=base_url,
            dimensions=config.dimensions,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )
    else:
        raise ValueError(f"不支持的 embedding provider: {config.provider}")

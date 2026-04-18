"""Embedding 统一接口：支持本地 ONNX 和云端 API"""

from pathlib import Path
from typing import Protocol
import numpy as np

from src.config import EmbeddingConfig


class EmbedderProtocol(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


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


class OpenAIEmbedder:
    """OpenAI API embedding"""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(input=texts, model=self.model)
        return [item.embedding for item in response.data]


def create_embedder(config: EmbeddingConfig) -> EmbedderProtocol:
    if config.provider == "local":
        return ONNXEmbedder(config.local_model, config.model_dir)
    elif config.provider == "openai":
        if not config.openai_api_key:
            raise ValueError("openai_api_key 未配置")
        return OpenAIEmbedder(config.openai_api_key, config.openai_model)
    else:
        raise ValueError(f"不支持的 embedding provider: {config.provider}")

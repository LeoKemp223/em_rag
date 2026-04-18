"""端到端测试：使用 ChromaDB 内置 embedding 验证完整 pipeline（无需 ONNX 模型）"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import load_config, EmbeddingConfig
from src.parser import DocElement
from src.element_classifier import ElementClassifier
from src.chunker import Chunker
from src.store import VectorStore, FTSStore
from src.retriever import Retriever


class ChromaDefaultEmbedder:
    """使用 ChromaDB 内置 embedding（all-MiniLM-L6-v2，自动下载）作为 fallback"""

    def __init__(self):
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
        self._fn = DefaultEmbeddingFunction()

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._fn(texts)


def create_test_elements() -> list[DocElement]:
    """模拟 STM32 SPI 章节的解析结果"""
    return [
        DocElement(type="heading", content="Serial peripheral interface (SPI)",
                   context_chain="SPI", level=1, page=0),
        DocElement(type="text",
                   content="The SPI interface provides a synchronous serial communication link. "
                           "It supports full-duplex, half-duplex, and simplex modes.",
                   context_chain="SPI", page=0),
        DocElement(type="heading", content="SPI registers",
                   context_chain="SPI > SPI registers", level=2, page=1),
        DocElement(type="heading", content="SPI control register 1 (SPI_CR1)",
                   context_chain="SPI > SPI registers > SPI_CR1", level=3, page=1),
        DocElement(type="text",
                   content="Address offset: 0x00. Reset value: 0x0000.",
                   context_chain="SPI > SPI registers > SPI_CR1", page=1),
        DocElement(type="table",
                   content="| Bit | Name | Description |\n| --- | --- | --- |\n"
                           "| 15 | BIDIMODE | Bidirectional data mode enable |\n"
                           "| 14 | BIDIOE | Output enable in bidirectional mode |\n"
                           "| 11 | DFF | Data frame format (0=8bit, 1=16bit) |\n"
                           "| 9 | SSM | Software slave management |\n"
                           "| 6 | SPE | SPI enable |\n"
                           "| 5:3 | BR[2:0] | Baud rate control (000=/2, 001=/4, ...) |\n"
                           "| 2 | MSTR | Master selection |\n"
                           "| 1 | CPOL | Clock polarity |\n"
                           "| 0 | CPHA | Clock phase |",
                   context_chain="SPI > SPI registers > SPI_CR1", page=1,
                   metadata={"row_count": 10}),
        DocElement(type="heading", content="SPI control register 2 (SPI_CR2)",
                   context_chain="SPI > SPI registers > SPI_CR2", level=3, page=2),
        DocElement(type="table",
                   content="| Bit | Name | Description |\n| --- | --- | --- |\n"
                           "| 7 | TXEIE | Tx buffer empty interrupt enable |\n"
                           "| 6 | RXNEIE | Rx buffer not empty interrupt enable |\n"
                           "| 1 | TXDMAEN | Tx buffer DMA enable |\n"
                           "| 0 | RXDMAEN | Rx buffer DMA enable |",
                   context_chain="SPI > SPI registers > SPI_CR2", page=2,
                   metadata={"row_count": 5}),
        DocElement(type="heading", content="DMA configuration",
                   context_chain="SPI > DMA configuration", level=2, page=3),
        DocElement(type="text",
                   content="To use DMA with SPI, enable TXDMAEN or RXDMAEN in SPI_CR2. "
                           "Configure DMA channel: SPI1_TX uses DMA1 Channel3, SPI1_RX uses DMA1 Channel2. "
                           "Set the DMA_CCR register with proper direction, memory increment, and data size.",
                   context_chain="SPI > DMA configuration", page=3),
    ]


def main():
    print("=" * 60)
    print("em_rag 端到端测试（使用 ChromaDB 内置 embedding）")
    print("=" * 60)

    config = load_config()

    # 使用临时目录避免污染正式数据
    import tempfile
    tmp = tempfile.mkdtemp()
    config.storage.chroma_path = f"{tmp}/chroma"
    config.storage.fts_path = f"{tmp}/fts.db"

    print("\n[1] 创建测试数据...")
    elements = create_test_elements()
    print(f"    {len(elements)} 个元素")

    print("\n[2] 元素分类...")
    classifier = ElementClassifier()
    elements = classifier.classify(elements)
    type_counts = {}
    for el in elements:
        type_counts[el.type] = type_counts.get(el.type, 0) + 1
    print(f"    类型分布: {type_counts}")

    print("\n[3] 分块...")
    chunker = Chunker(config.chunking)
    chunks = chunker.chunk(elements)
    print(f"    生成 {len(chunks)} 个 chunks")
    for i, c in enumerate(chunks):
        print(f"    [{i}] type={c.element_type}, ctx={c.context_chain}, kw={c.keywords[:3]}")

    print("\n[4] Embedding + 存储...")
    embedder = ChromaDefaultEmbedder()
    texts = [c.content for c in chunks]
    embeddings = embedder.embed(texts)
    print(f"    embedding 维度: {len(embeddings[0])}")

    vector_store = VectorStore(config.storage)
    vector_store.add_chunks(chunks, embeddings, "stm32f4_test")

    fts_store = FTSStore(config.storage)
    fts_store.add_chunks(chunks, "stm32f4_test")

    print("\n[5] 检索测试...")
    retriever = Retriever(config.retrieval, embedder, vector_store, fts_store)

    queries = [
        "SPI_CR1 寄存器位域",
        "SPI DMA 发送配置",
        "SPI 波特率设置",
        "TXDMAEN",
    ]

    for q in queries:
        print(f"\n  查询: '{q}'")
        results = retriever.search(q, top_k=3)
        for i, r in enumerate(results):
            preview = r.content[:80].replace("\n", " ")
            print(f"    [{i+1}] ({r.source}) {r.context_chain} → {preview}...")

    # 清理
    fts_store.close()
    import shutil
    shutil.rmtree(tmp)

    print("\n" + "=" * 60)
    print("测试通过! Pipeline 完整可用。")
    print("=" * 60)


if __name__ == "__main__":
    main()

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.chunker import Chunk
from src.config import RetrievalConfig, StorageConfig
from src.retriever import Retriever
from src.store import FTSStore


class DummyEmbedder:
    def embed(self, texts):
        return [[0.0, 1.0] for _ in texts]


class DummyVectorStore:
    def search(self, query_embedding, top_k=5, doc_filter=None):
        return []


def test_fts_search_filters_docs_and_retriever_expands_context(tmp_path):
    store = FTSStore(StorageConfig(fts_path=str(tmp_path / "fts.db")))
    chunks = [
        Chunk(
            content="Figure summary:\nI2C write cycle timing uses SCL SDA ACK.",
            context_chain="AT24C02 > Write cycle",
            element_type="figure",
            page=6,
            metadata={
                "related_images": [
                    {
                        "image_path": "data/figures/at24c02/page_7_full.png",
                        "summary": "I2C write cycle timing uses SCL SDA ACK.",
                        "asset_type": "full_page",
                    }
                ]
            },
        ),
        Chunk(
            content="The write cycle starts after START and device address.",
            context_chain="AT24C02 > Write cycle",
            element_type="text",
            page=6,
        ),
    ]
    store.add_chunks(chunks, "at24c02")
    store.add_chunks(
        [
            Chunk(
                content="SPI timing uses SCLK and MOSI.",
                context_chain="SPI",
                element_type="text",
                page=1,
            )
        ],
        "spi_doc",
    )

    retriever = Retriever(
        RetrievalConfig(top_k=3, context_expand=True),
        DummyEmbedder(),
        DummyVectorStore(),
        store,
    )

    results = retriever.search("SCL SDA ACK", doc_filter="at24c02")

    assert results
    assert results[0].doc_id == "at24c02"
    assert results[0].element_type == "figure"
    assert results[0].related_images[0]["image_path"] == (
        "data/figures/at24c02/page_7_full.png"
    )
    assert any(ctx["element_type"] == "text" for ctx in results[0].expanded_context)

    store.close()


def test_timing_queries_prioritize_figure_chunks(tmp_path):
    store = FTSStore(StorageConfig(fts_path=str(tmp_path / "fts.db")))
    chunks = [
        Chunk(
            content="Electrical timing table includes tSU and tHD for SCL SDA.",
            context_chain="AT24C02 > AC characteristics",
            element_type="text",
            page=3,
            metadata={
                "related_images": [
                    {
                        "image_path": "data/figures/at24c02/page_4_full.png",
                        "summary": "Timing diagram with tSU tHD SCL SDA.",
                    }
                ]
            },
        ),
        Chunk(
            content="Figure summary:\nTiming diagram with tSU tHD SCL SDA.",
            context_chain="AT24C02 > AC characteristics",
            element_type="figure",
            page=3,
            metadata={
                "related_images": [
                    {
                        "image_path": "data/figures/at24c02/page_4_full.png",
                        "summary": "Timing diagram with tSU tHD SCL SDA.",
                    }
                ]
            },
        ),
    ]
    store.add_chunks(chunks, "at24c02")

    results = store.search(["tSU", "tHD"], top_k=2, doc_filter="at24c02")

    assert results[0]["metadata"]["element_type"] == "figure"
    store.close()


def test_chinese_query_aliases_match_english_semantic_hints(tmp_path):
    store = FTSStore(StorageConfig(fts_path=str(tmp_path / "fts.db")))
    store.add_chunks(
        [
            Chunk(
                content="Figure summary:\nsemantic hints: page write, ACK polling.",
                context_chain="AT24C02 > Write",
                element_type="figure",
                page=8,
            )
        ],
        "at24c02",
    )

    results = store.search(["页写"], top_k=1, doc_filter="at24c02")

    assert results
    assert results[0]["metadata"]["element_type"] == "figure"
    store.close()


def test_retriever_extracts_timing_keywords():
    retriever = Retriever(
        RetrievalConfig(),
        DummyEmbedder(),
        DummyVectorStore(),
        None,
    )

    assert {"tSU", "tHD", "SCL", "SDA"} <= set(
        retriever._extract_keywords("tSU tHD SCL SDA")
    )
    assert {"页写", "应答查询", "随机读"} <= set(
        retriever._extract_keywords("页写 应答查询 随机读")
    )
    assert {"page write", "ACK polling", "random read"} <= set(
        retriever._extract_keywords("页写 应答查询 随机读")
    )

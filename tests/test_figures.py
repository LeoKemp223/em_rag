import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.chunker import Chunker
from src.config import ChunkingConfig, FiguresConfig
from src.parsers import DocElement

pytest.importorskip("fitz")
from src.parsers.pdf_parser import PdfParser


def test_chunker_attaches_related_images_to_same_page_chunks():
    elements = [
        DocElement(
            type="heading",
            content="SPI timing",
            context_chain="SPI timing",
            level=1,
            page=4,
        ),
        DocElement(
            type="figure",
            content="Timing diagram image: SPI timing waveform",
            context_chain="SPI timing",
            page=4,
            metadata={
                "image_path": "data/figures/stm32/page_5_full.png",
                "page": 4,
                "bbox": None,
                "caption": "SPI timing waveform",
                "figure_type": "timing_diagram",
                "asset_type": "full_page",
            },
        ),
        DocElement(
            type="text",
            content="The SPI interface samples MOSI on the SCLK rising edge.",
            context_chain="SPI timing",
            page=4,
        ),
    ]

    chunks = Chunker(ChunkingConfig()).chunk(elements)
    text_chunk = next(chunk for chunk in chunks if chunk.element_type == "text")

    assert text_chunk.metadata["related_images"][0]["image_path"] == (
        "data/figures/stm32/page_5_full.png"
    )
    assert "SPI timing waveform" in text_chunk.metadata["related_images"][0]["summary"]
    assert "SPI timing waveform" not in text_chunk.retrieval_text


def test_chunker_indexes_figure_summary_as_retrieval_text():
    elements = [
        DocElement(
            type="figure",
            content="Timing diagram image: I2C write cycle",
            context_chain="AT24C02 > Write cycle",
            page=6,
            metadata={
                "image_path": "data/figures/at24c02/page_7_full.png",
                "page": 6,
                "caption": "I2C write cycle timing",
                "signals": ["SCL", "SDA", "ACK"],
                "asset_type": "full_page",
                "detection_method": "heuristic",
            },
        )
    ]

    chunk = Chunker(ChunkingConfig()).chunk(elements)[0]

    assert chunk.element_type == "figure"
    assert "I2C write cycle timing" in chunk.content
    assert "SCL" in chunk.retrieval_text
    assert "data/figures/at24c02/page_7_full.png" in chunk.retrieval_text
    assert chunk.content.count("Figure summary:") == 1


def test_pdf_parser_detects_timing_related_text_without_word_boundary_for_chinese():
    parser = PdfParser(FiguresConfig(enabled=True))

    assert parser._should_save_figure_page("图 12 I2C 总线时序")
    assert parser._should_save_figure_page("Figure 5. SPI timing diagram")
    assert not parser._should_save_figure_page("Electrical characteristics")


def test_pdf_parser_hybrid_candidate_uses_broad_timing_signals():
    parser = PdfParser(FiguresConfig(enabled=True, detection="hybrid"))

    class Page:
        def get_text(self, _format):
            return {"blocks": []}

        def get_drawings(self):
            return []

    assert parser._is_candidate_page("AC switching characteristics read cycle", Page())
    assert parser._is_candidate_page("建立时间和保持时间参数", Page())
    assert not parser._is_candidate_page("Package ordering information", Page())


def test_pdf_parser_extracts_figure_caption_and_semantic_hints():
    parser = PdfParser(FiguresConfig(enabled=True))
    text = """
    图10页写
    24C02器件按8字节/页执行页写。
    EEPROM收到每个数据后都应答“0”。
    SDA 线
    """

    assert parser._extract_caption(text) == "图10页写"
    hints = parser._extract_semantic_hints(text)
    assert "page write" in hints
    assert "ACK acknowledge" in hints
    assert "图10页写" in hints

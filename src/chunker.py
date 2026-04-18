"""元素感知分块器：按元素类型和语义边界切分 chunk"""

from dataclasses import dataclass, field
from src.parser import DocElement
from src.config import ChunkingConfig


@dataclass
class Chunk:
    content: str
    context_chain: str
    element_type: str
    page: int
    metadata: dict = field(default_factory=dict)
    keywords: list[str] = field(default_factory=list)

    @property
    def token_estimate(self) -> int:
        return len(self.content) // 3


class Chunker:
    def __init__(self, config: ChunkingConfig):
        self.max_tokens = config.max_tokens
        self.overlap_tokens = config.overlap_tokens
        self.keep_tables_intact = config.keep_tables_intact
        self.split_at_boundary = config.split_at_semantic_boundary

    def chunk(self, elements: list[DocElement]) -> list[Chunk]:
        chunks: list[Chunk] = []
        text_buffer: list[DocElement] = []
        current_context = ""

        for el in elements:
            if el.type == "heading":
                if text_buffer:
                    chunks.extend(self._flush_text_buffer(text_buffer, current_context))
                    text_buffer = []
                current_context = el.context_chain
                continue

            if el.type == "table" and self.keep_tables_intact:
                if text_buffer:
                    chunks.extend(self._flush_text_buffer(text_buffer, current_context))
                    text_buffer = []
                chunks.append(self._make_table_chunk(el))
                continue

            if el.type == "code":
                if text_buffer:
                    chunks.extend(self._flush_text_buffer(text_buffer, current_context))
                    text_buffer = []
                chunks.append(Chunk(
                    content=el.content,
                    context_chain=el.context_chain or current_context,
                    element_type="code",
                    page=el.page,
                ))
                continue

            if el.type == "list":
                if text_buffer:
                    chunks.extend(self._flush_text_buffer(text_buffer, current_context))
                    text_buffer = []
                chunks.append(Chunk(
                    content=el.content,
                    context_chain=el.context_chain or current_context,
                    element_type="list",
                    page=el.page,
                ))
                continue

            # text 类型：累积到 buffer
            if self.split_at_boundary and text_buffer:
                if self._should_split(text_buffer, el):
                    chunks.extend(self._flush_text_buffer(text_buffer, current_context))
                    text_buffer = []

            text_buffer.append(el)

        if text_buffer:
            chunks.extend(self._flush_text_buffer(text_buffer, current_context))

        # 提取关键词
        for chunk in chunks:
            chunk.keywords = self._extract_keywords(chunk.content)

        return chunks

    def _should_split(self, buffer: list[DocElement], new_el: DocElement) -> bool:
        """语义边界检测"""
        current_tokens = sum(len(el.content) // 3 for el in buffer)
        new_tokens = len(new_el.content) // 3

        if current_tokens + new_tokens > self.max_tokens:
            return True

        if buffer and buffer[-1].context_chain != new_el.context_chain:
            return True

        return False

    def _flush_text_buffer(
        self, buffer: list[DocElement], fallback_context: str
    ) -> list[Chunk]:
        """将文本 buffer 转为 chunk，超长时切分"""
        if not buffer:
            return []

        combined = "\n\n".join(el.content for el in buffer)
        context = buffer[0].context_chain or fallback_context
        page = buffer[0].page

        token_est = len(combined) // 3
        if token_est <= self.max_tokens:
            return [Chunk(
                content=combined,
                context_chain=context,
                element_type="text",
                page=page,
            )]

        # 超长文本按段落切分
        return self._split_long_text(combined, context, page)

    def _split_long_text(self, text: str, context: str, page: int) -> list[Chunk]:
        """按段落边界切分超长文本"""
        paragraphs = text.split("\n\n")
        chunks: list[Chunk] = []
        current_parts: list[str] = []
        current_tokens = 0

        for para in paragraphs:
            para_tokens = len(para) // 3
            if current_tokens + para_tokens > self.max_tokens and current_parts:
                chunks.append(Chunk(
                    content="\n\n".join(current_parts),
                    context_chain=context,
                    element_type="text",
                    page=page,
                ))
                # overlap: 保留最后一段
                if self.overlap_tokens > 0 and current_parts:
                    last = current_parts[-1]
                    current_parts = [last]
                    current_tokens = len(last) // 3
                else:
                    current_parts = []
                    current_tokens = 0

            current_parts.append(para)
            current_tokens += para_tokens

        if current_parts:
            chunks.append(Chunk(
                content="\n\n".join(current_parts),
                context_chain=context,
                element_type="text",
                page=page,
            ))

        return chunks

    def _make_table_chunk(self, el: DocElement) -> Chunk:
        """表格作为独立 chunk，前置 context_chain"""
        header = f"[{el.context_chain}]\n\n" if el.context_chain else ""
        return Chunk(
            content=header + el.content,
            context_chain=el.context_chain,
            element_type="table",
            page=el.page,
            metadata=el.metadata.copy(),
        )

    def _extract_keywords(self, text: str) -> list[str]:
        """提取寄存器名、外设名等关键词"""
        import re
        register_pattern = r'\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b'
        peripheral_pattern = r'\b(?:SPI|GPIO|UART|USART|TIM|I2C|DMA|ADC|DAC|RTC|WWDG|IWDG|CAN|USB|ETH|SDIO|FSMC)\b'
        matches = re.findall(f"{register_pattern}|{peripheral_pattern}", text)
        return list(set(matches))

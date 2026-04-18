"""元素分类器：对 DocParser 输出的元素做二次分类和 context_chain 增强"""

import re
from src.parser import DocElement


class ElementClassifier:
    """对 text 类型元素做二次分类，识别其中的列表、代码块等"""

    def classify(self, elements: list[DocElement]) -> list[DocElement]:
        result: list[DocElement] = []
        heading_stack: list[tuple[int, str]] = []

        for el in elements:
            if el.type == "heading":
                self._update_stack(heading_stack, el.level, el.content)
                result.append(el)
                continue

            if el.type == "table":
                if not el.context_chain and heading_stack:
                    el.context_chain = self._chain_from_stack(heading_stack)
                result.append(el)
                continue

            if el.type == "text":
                sub_elements = self._split_text_element(el, heading_stack)
                result.extend(sub_elements)
                continue

            result.append(el)

        return result

    def _split_text_element(
        self, el: DocElement, heading_stack: list[tuple[int, str]]
    ) -> list[DocElement]:
        """将 text 元素中的列表和代码块拆分出来"""
        content = el.content
        parts: list[DocElement] = []

        lines = content.split("\n")
        buffer: list[str] = []
        buffer_type = "text"

        for line in lines:
            line_type = self._detect_line_type(line)

            if line_type != buffer_type and buffer:
                parts.append(self._make_element(
                    buffer_type, "\n".join(buffer), el, heading_stack
                ))
                buffer = []

            buffer_type = line_type
            buffer.append(line)

        if buffer:
            parts.append(self._make_element(
                buffer_type, "\n".join(buffer), el, heading_stack
            ))

        # 检测文本中的 Markdown 标题（fallback，无书签时）
        enhanced = []
        for part in parts:
            if part.type == "text":
                sub = self._extract_markdown_headings(part, heading_stack)
                enhanced.extend(sub)
            else:
                enhanced.append(part)

        return enhanced

    def _detect_line_type(self, line: str) -> str:
        stripped = line.strip()
        if not stripped:
            return "text"
        if re.match(r'^[-*+]\s', stripped) or re.match(r'^\d+\.\s', stripped):
            return "list"
        if stripped.startswith("```"):
            return "code"
        return "text"

    def _make_element(
        self,
        elem_type: str,
        content: str,
        original: DocElement,
        heading_stack: list[tuple[int, str]],
    ) -> DocElement:
        ctx = original.context_chain or self._chain_from_stack(heading_stack)
        return DocElement(
            type=elem_type,
            content=content.strip(),
            context_chain=ctx,
            page=original.page,
            metadata=original.metadata.copy(),
        )

    def _extract_markdown_headings(
        self, el: DocElement, heading_stack: list[tuple[int, str]]
    ) -> list[DocElement]:
        """从文本中提取 Markdown 标题，拆分为 heading + text"""
        lines = el.content.split("\n")
        result: list[DocElement] = []
        text_buffer: list[str] = []

        for line in lines:
            match = re.match(r'^(#{1,6})\s+(.+)', line.strip())
            if match:
                if text_buffer:
                    result.append(DocElement(
                        type="text",
                        content="\n".join(text_buffer).strip(),
                        context_chain=self._chain_from_stack(heading_stack),
                        page=el.page,
                        metadata=el.metadata.copy(),
                    ))
                    text_buffer = []

                level = len(match.group(1))
                title = match.group(2).strip()
                self._update_stack(heading_stack, level, title)
                result.append(DocElement(
                    type="heading",
                    content=title,
                    context_chain=self._chain_from_stack(heading_stack),
                    level=level,
                    page=el.page,
                ))
            else:
                text_buffer.append(line)

        if text_buffer:
            content = "\n".join(text_buffer).strip()
            if content:
                result.append(DocElement(
                    type="text",
                    content=content,
                    context_chain=self._chain_from_stack(heading_stack),
                    page=el.page,
                    metadata=el.metadata.copy(),
                ))

        return result if result else [el]

    def _update_stack(self, stack: list[tuple[int, str]], level: int, title: str):
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))

    def _chain_from_stack(self, stack: list[tuple[int, str]]) -> str:
        return " > ".join(title for _, title in stack)

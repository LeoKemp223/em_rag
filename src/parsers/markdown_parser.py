"""Markdown 文档解析器"""

import re
from pathlib import Path
from . import DocElement


class MarkdownParser:
    def parse(self, file_path: str) -> list[DocElement]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        text = path.read_text(encoding="utf-8")
        elements: list[DocElement] = []
        heading_stack: list[str] = []
        buffer: list[str] = []
        in_code_block = False
        code_lines: list[str] = []

        def flush_buffer():
            content = "\n".join(buffer).strip()
            if content:
                elements.append(DocElement(
                    type="text", content=content,
                    context_chain=" > ".join(heading_stack),
                ))
            buffer.clear()

        for line in text.split("\n"):
            # 代码块
            if line.strip().startswith("```"):
                if in_code_block:
                    elements.append(DocElement(
                        type="code", content="\n".join(code_lines),
                        context_chain=" > ".join(heading_stack),
                    ))
                    code_lines.clear()
                    in_code_block = False
                else:
                    flush_buffer()
                    in_code_block = True
                continue

            if in_code_block:
                code_lines.append(line)
                continue

            # 标题
            m = re.match(r"^(#{1,6})\s+(.+)", line)
            if m:
                flush_buffer()
                level = len(m.group(1))
                title = m.group(2).strip()
                while len(heading_stack) >= level:
                    heading_stack.pop()
                heading_stack.append(title)
                elements.append(DocElement(
                    type="heading", content=title,
                    context_chain=" > ".join(heading_stack), level=level,
                ))
                continue

            # 表格行
            if line.strip().startswith("|") and line.strip().endswith("|"):
                if not buffer or not buffer[-1].strip().startswith("|"):
                    flush_buffer()
                buffer.append(line)
                continue

            # 列表项
            if re.match(r"^\s*[-*+]\s", line) or re.match(r"^\s*\d+\.\s", line):
                if not buffer or not (re.match(r"^\s*[-*+]\s", buffer[-1]) or re.match(r"^\s*\d+\.\s", buffer[-1])):
                    flush_buffer()
                buffer.append(line)
                continue

            # 普通文本
            buffer.append(line)

        flush_buffer()

        # 后处理：将连续表格行合并为 table 类型
        merged: list[DocElement] = []
        for el in elements:
            if el.type == "text" and el.content.strip().startswith("|"):
                lines = el.content.strip().split("\n")
                if len(lines) >= 2:
                    el = DocElement(
                        type="table", content=el.content.strip(),
                        context_chain=el.context_chain,
                        metadata={"row_count": len(lines)},
                    )
            merged.append(el)

        return merged

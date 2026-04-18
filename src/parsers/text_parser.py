"""纯文本解析器"""

import re
from pathlib import Path
from . import DocElement


class TextParser:
    def parse(self, file_path: str) -> list[DocElement]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        text = path.read_text(encoding="utf-8", errors="replace")
        base_context = path.name
        elements: list[DocElement] = []

        # 按空行或分隔线分块
        blocks = re.split(r"\n\s*\n|\n[=\-]{3,}\n", text)

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            el_type = "text"
            # 检测对齐表格（多行含 | 或 tab 对齐列）
            lines = block.split("\n")
            if len(lines) >= 2:
                pipe_lines = sum(1 for l in lines if "|" in l)
                if pipe_lines >= len(lines) * 0.6:
                    el_type = "table"
                elif all("\t" in l for l in lines[:3]):
                    el_type = "table"

            elements.append(DocElement(
                type=el_type, content=block,
                context_chain=base_context,
            ))

        return elements

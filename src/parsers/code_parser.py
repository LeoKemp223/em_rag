"""代码文件解析器（.h/.c/.s）— 识别寄存器宏、结构体、函数"""

import re
from pathlib import Path
from . import DocElement


class CodeParser:
    def parse(self, file_path: str) -> list[DocElement]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        text = path.read_text(encoding="utf-8", errors="replace")
        suffix = path.suffix.lower()
        base_context = path.name

        if suffix == ".s":
            return self._parse_asm(text, base_context)
        return self._parse_c(text, base_context)

    def _parse_c(self, text: str, base_context: str) -> list[DocElement]:
        elements: list[DocElement] = []

        # 提取 #define 寄存器宏，按前缀分组
        defines = re.findall(
            r"^[ \t]*#define\s+([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*)\s+(.+)",
            text, re.MULTILINE,
        )
        groups: dict[str, list[str]] = {}
        for name, value in defines:
            parts = name.split("_")
            prefix = "_".join(parts[:2]) if len(parts) >= 2 else parts[0]
            groups.setdefault(prefix, []).append(f"#define {name}  {value.strip()}")

        for prefix, lines in groups.items():
            elements.append(DocElement(
                type="code", content="\n".join(lines),
                context_chain=f"{base_context} > {prefix}",
                metadata={"register_prefix": prefix, "define_count": len(lines)},
            ))

        # 提取 typedef struct 块
        for m in re.finditer(
            r"typedef\s+struct\s*\{[^}]*\}\s*(\w+)\s*;",
            text, re.DOTALL,
        ):
            elements.append(DocElement(
                type="code", content=m.group(0),
                context_chain=f"{base_context} > {m.group(1)}",
                metadata={"struct_name": m.group(1)},
            ))

        # 提取函数定义
        for m in re.finditer(
            r"^[\w\s\*]+?\s+(\w+)\s*\([^)]*\)\s*\{",
            text, re.MULTILINE,
        ):
            func_name = m.group(1)
            if func_name in ("if", "while", "for", "switch"):
                continue
            end = text.find("}", m.start())
            body = text[m.start():end + 1] if end != -1 else text[m.start():m.start() + 500]
            elements.append(DocElement(
                type="code", content=body,
                context_chain=f"{base_context} > {func_name}",
                metadata={"function": func_name},
            ))

        # 如果没有识别到结构化内容，按块分割
        if not elements:
            elements = self._fallback_split(text, base_context)

        return elements

    def _parse_asm(self, text: str, base_context: str) -> list[DocElement]:
        elements: list[DocElement] = []
        current_section = base_context

        # 提取 EQU 定义
        equs = re.findall(r"^(\w+)\s+(?:EQU|\.equ)\s+(.+)", text, re.MULTILINE | re.IGNORECASE)
        if equs:
            content = "\n".join(f"{name}  EQU  {val.strip()}" for name, val in equs)
            elements.append(DocElement(
                type="code", content=content,
                context_chain=f"{base_context} > EQU definitions",
            ))

        # 按 section/label 分块
        blocks = re.split(r"^(\w+:)", text, flags=re.MULTILINE)
        for i in range(1, len(blocks), 2):
            label = blocks[i].rstrip(":")
            body = blocks[i + 1] if i + 1 < len(blocks) else ""
            if body.strip():
                elements.append(DocElement(
                    type="code", content=f"{label}:\n{body.strip()}",
                    context_chain=f"{base_context} > {label}",
                ))

        if not elements:
            elements = self._fallback_split(text, base_context)

        return elements

    def _fallback_split(self, text: str, base_context: str) -> list[DocElement]:
        elements: list[DocElement] = []
        blocks = re.split(r"\n\s*\n", text)
        for block in blocks:
            block = block.strip()
            if block:
                elements.append(DocElement(
                    type="code", content=block,
                    context_chain=base_context,
                ))
        return elements

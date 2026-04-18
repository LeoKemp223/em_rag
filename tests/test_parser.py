"""验证 PDF 解析效果的测试脚本

用法：
    python3 tests/test_parser.py <pdf_path>

输出解析结果摘要，用于验证 PyMuPDF + pdfplumber 双通道效果。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parser import DocParser


def main():
    if len(sys.argv) < 2:
        print("用法: python3 tests/test_parser.py <pdf_path>")
        print("示例: python3 tests/test_parser.py ./data/documents/STM32F4_Reference_Manual.pdf")
        sys.exit(1)

    pdf_path = sys.argv[1]
    print(f"解析文件: {pdf_path}")
    print("=" * 60)

    parser = DocParser()
    elements = parser.parse(pdf_path)

    type_counts = {}
    for el in elements:
        type_counts[el.type] = type_counts.get(el.type, 0) + 1

    print(f"\n总元素数: {len(elements)}")
    print(f"类型分布: {type_counts}")
    print(f"页数覆盖: {len(set(el.page for el in elements))}")

    headings = [el for el in elements if el.type == "heading"]
    print(f"\n书签/标题数: {len(headings)}")
    if headings:
        print("前 10 个标题:")
        for h in headings[:10]:
            indent = "  " * (h.level - 1)
            print(f"  {indent}[L{h.level}] {h.content}")

    tables = [el for el in elements if el.type == "table"]
    print(f"\n表格数: {len(tables)}")
    if tables:
        print("\n前 3 个表格预览:")
        for i, t in enumerate(tables[:3]):
            print(f"\n  --- 表格 {i+1} (p.{t.page+1}) context: {t.context_chain} ---")
            lines = t.content.split("\n")
            for line in lines[:5]:
                print(f"  {line}")
            if len(lines) > 5:
                print(f"  ... ({len(lines)} 行)")

    texts = [el for el in elements if el.type == "text"]
    print(f"\n文本块数: {len(texts)}")
    if texts:
        print("\n前 3 个文本块预览:")
        for i, t in enumerate(texts[:3]):
            preview = t.content[:150].replace("\n", " ")
            print(f"  [{i+1}] (p.{t.page+1}) {t.context_chain}")
            print(f"      {preview}...")

    print("\n" + "=" * 60)
    print("验证完成。请检查：")
    print("  1. 表格是否正确提取（行列对齐）")
    print("  2. context_chain 是否反映文档层级结构")
    print("  3. 书签/标题是否完整")


if __name__ == "__main__":
    main()

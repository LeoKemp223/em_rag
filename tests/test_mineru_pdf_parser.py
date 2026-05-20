import stat
import sys
import os
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import ParsingConfig
from src.parsers import create_parser
from src.parsers.mineru_pdf_parser import MinerUPdfParser


def test_create_parser_selects_mineru_backend(tmp_path):
    parser = create_parser(
        str(tmp_path / "sample.pdf"),
        ParsingConfig(pdf_backend="mineru"),
    )

    assert isinstance(parser, MinerUPdfParser)


def test_mineru_parser_reports_missing_command(tmp_path):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    parser = MinerUPdfParser(
        ParsingConfig(
            pdf_backend="mineru",
            mineru_command="__missing_mineru_for_test__",
            mineru_output_dir=str(tmp_path / "out"),
        )
    )

    with pytest.raises(RuntimeError, match="未找到 MinerU 命令"):
        parser.parse(str(pdf))


def test_mineru_parser_reuses_generated_markdown(tmp_path, monkeypatch):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_mineru = bin_dir / "mineru"
    fake_mineru.write_text(
        """#!/usr/bin/env sh
out=""
stem=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -p) shift; stem=$(basename "$1" .pdf) ;;
    -o) shift; out="$1" ;;
  esac
  shift
done
mkdir -p "$out/$stem/auto"
cat > "$out/$stem/auto/$stem.md" <<'EOF'
# Device

| Pin | Name |
| --- | --- |
| 1 | VCC |
EOF
""",
        encoding="utf-8",
    )
    fake_mineru.chmod(fake_mineru.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    parser = MinerUPdfParser(
        ParsingConfig(
            pdf_backend="mineru",
            mineru_command="mineru",
            mineru_output_dir=str(tmp_path / "out"),
        )
    )

    elements = parser.parse(str(pdf))

    assert [el.type for el in elements] == ["heading", "table"]
    assert elements[0].metadata["parser"] == "mineru"
    assert elements[1].metadata["source_pdf"] == str(pdf.resolve())

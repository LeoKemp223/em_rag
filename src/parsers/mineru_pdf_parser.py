"""MinerU-backed PDF parser."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

from . import DocElement
from .markdown_parser import MarkdownParser


class MinerUPdfParser:
    def __init__(self, parsing_config=None, figures_config=None):
        self.parsing_config = parsing_config
        self.figures_config = figures_config

    def parse(self, pdf_path: str) -> list[DocElement]:
        path = Path(pdf_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {pdf_path}")
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"不是 PDF 格式: {path.suffix}")

        command = getattr(self.parsing_config, "mineru_command", "mineru")
        if not shutil.which(command):
            raise RuntimeError(
                f"未找到 MinerU 命令: {command}。请先安装 MinerU，"
                "或将 parsing.pdf_backend 改回 pymupdf。"
            )

        output_root = Path(
            getattr(self.parsing_config, "mineru_output_dir", "./data/mineru")
        ).expanduser().resolve()
        run_dir = output_root / path.stem
        run_dir.mkdir(parents=True, exist_ok=True)

        subprocess.run(
            [
                command,
                "-p",
                str(path),
                "-o",
                str(run_dir),
                *getattr(self.parsing_config, "mineru_args", []),
            ],
            check=True,
        )

        markdown_path = self._find_markdown_output(run_dir, path.stem)
        elements = MarkdownParser().parse(str(markdown_path))
        for el in elements:
            el.metadata.setdefault("parser", "mineru")
            el.metadata.setdefault("source_pdf", str(path))
            el.metadata.setdefault("mineru_markdown", str(markdown_path))
        return elements

    def _find_markdown_output(self, run_dir: Path, stem: str) -> Path:
        preferred = [
            run_dir / f"{stem}.md",
            run_dir / stem / f"{stem}.md",
            run_dir / stem / "auto" / f"{stem}.md",
        ]
        for candidate in preferred:
            if candidate.exists():
                return candidate

        markdown_files = sorted(run_dir.rglob("*.md"))
        if not markdown_files:
            raise FileNotFoundError(f"MinerU 未生成 Markdown 文件: {run_dir}")
        return markdown_files[0]

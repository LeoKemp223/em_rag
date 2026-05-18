"""双通道 PDF 解析：PyMuPDF（文本+书签/图片） + pdfplumber（表格）"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re

import fitz
import pdfplumber

from . import DocElement
from .utils import table_to_markdown


class PdfParser:
    TIMING_KEYWORDS = (
        "timing",
        "waveform",
        "wave form",
        "timing diagram",
        "时序",
        "波形",
        "setup",
        "hold",
        "rise time",
        "fall time",
        "propagation delay",
        "tSU",
        "tHD",
        "tCLK",
        "tCSS",
        "tCSH",
        "SCL",
        "SDA",
        "SCLK",
        "MOSI",
        "MISO",
        "NSS",
        "CS",
        "CLK",
    )

    def __init__(self, config=None):
        self.figure_config = config
        self._llm_client = None

    def parse(self, pdf_path: str) -> list[DocElement]:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {pdf_path}")
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"不是 PDF 格式: {path.suffix}")

        doc = fitz.open(pdf_path)
        bookmarks = self._extract_bookmarks(doc)
        pages_text = self._extract_pages(doc)
        figures_by_page = self._extract_figures(doc, path, pages_text)
        doc.close()

        tables_by_page = self._extract_tables(pdf_path)
        return self._merge(pages_text, tables_by_page, figures_by_page, bookmarks)

    def _extract_bookmarks(self, doc: fitz.Document) -> list[dict]:
        toc = doc.get_toc(simple=True)
        return [{"level": level, "title": title.strip(), "page": page - 1}
                for level, title, page in toc]

    def _extract_pages(self, doc: fitz.Document) -> list[dict]:
        return [{"page": i, "text": doc[i].get_text("text")} for i in range(len(doc))]

    def _extract_tables(self, pdf_path: str) -> dict[int, list[str]]:
        tables_by_page: dict[int, list[str]] = {}
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                tables = page.extract_tables()
                if tables:
                    md_tables = [table_to_markdown(t) for t in tables]
                    md_tables = [m for m in md_tables if m]
                    if md_tables:
                        tables_by_page[page_num] = md_tables
        return tables_by_page

    def _extract_figures(
        self,
        doc: fitz.Document,
        path: Path,
        pages_text: list[dict],
    ) -> dict[int, list[dict]]:
        cfg = self.figure_config
        if not cfg or not getattr(cfg, "enabled", False):
            return {}

        figures_by_page: dict[int, list[dict]] = {}
        doc_id = path.stem.lower().replace(" ", "_")
        output_dir = Path(cfg.output_dir) / doc_id
        dpi = max(int(getattr(cfg, "render_dpi", 180)), 72)
        zoom = dpi / 72
        matrix = fitz.Matrix(zoom, zoom)
        text_by_page = {p["page"]: p.get("text", "") for p in pages_text}

        for page_num in range(len(doc)):
            page_text = text_by_page.get(page_num, "")
            page = doc[page_num]
            decision = self._figure_decision(page_text, page)
            if not decision["save"]:
                continue

            caption = decision.get("suggested_caption") or self._extract_caption(page_text)
            semantic_hints = self._extract_semantic_hints(page_text)
            page_figures: list[dict] = []
            output_dir.mkdir(parents=True, exist_ok=True)

            if getattr(cfg, "save_full_page", True):
                full_name = f"page_{page_num + 1}_full.png"
                full_path = output_dir / full_name
                self._render_page(page, matrix, full_path)
                page_figures.append({
                    "image_path": str(full_path),
                    "page": page_num,
                    "bbox": None,
                    "caption": caption,
                    "figure_type": "timing_diagram",
                    "asset_type": "full_page",
                    "detection_method": decision.get("method", "heuristic"),
                    "confidence": decision.get("confidence", 1.0),
                    "reason": decision.get("reason", ""),
                    "signals": decision.get("signals", []),
                    "semantic_hints": semantic_hints,
                })

            if getattr(cfg, "save_crops", True):
                for i, bbox in enumerate(self._image_block_bboxes(page), 1):
                    crop_name = f"page_{page_num + 1}_figure_{i}.png"
                    crop_path = output_dir / crop_name
                    self._render_page(page, matrix, crop_path, clip=fitz.Rect(bbox))
                    page_figures.append({
                        "image_path": str(crop_path),
                        "page": page_num,
                        "bbox": [round(v, 2) for v in bbox],
                        "caption": caption,
                        "figure_type": "timing_diagram",
                        "asset_type": "crop",
                        "detection_method": decision.get("method", "heuristic"),
                        "confidence": decision.get("confidence", 1.0),
                        "reason": decision.get("reason", ""),
                        "signals": decision.get("signals", []),
                        "semantic_hints": semantic_hints,
                    })

            if page_figures:
                figures_by_page[page_num] = page_figures

        return figures_by_page

    def _figure_decision(self, page_text: str, page: fitz.Page) -> dict:
        mode = getattr(self.figure_config, "mode", "timing_related")
        detection = getattr(self.figure_config, "detection", "heuristic")
        if mode == "all":
            return {
                "save": True,
                "method": "mode_all",
                "confidence": 1.0,
                "reason": "figures.mode is all",
                "signals": ["mode=all"],
            }

        if detection == "heuristic":
            return {
                "save": self._should_save_figure_page(page_text),
                "method": "heuristic",
                "confidence": 1.0,
                "reason": "matched timing-related keyword",
                "signals": self._matched_keywords(page_text),
            }

        if detection == "hybrid" and not self._is_candidate_page(page_text, page):
            return {
                "save": False,
                "method": "hybrid_candidate",
                "confidence": 0.0,
                "reason": "no broad local candidate signals",
                "signals": [],
            }

        if detection in ("hybrid", "llm"):
            return self._classify_page_with_llm(page_text, page)

        raise ValueError(
            f"不支持的 figures.detection: {detection} "
            "（支持: heuristic, hybrid, llm）"
        )

    def _should_save_figure_page(self, page_text: str) -> bool:
        mode = getattr(self.figure_config, "mode", "timing_related")
        if mode == "all":
            return True
        text = page_text or ""
        for keyword in self.TIMING_KEYWORDS:
            if self._contains_keyword(text, keyword):
                return True
        return False

    def _is_candidate_page(self, page_text: str, page: fitz.Page) -> bool:
        text = page_text or ""
        if self._should_save_figure_page(text):
            return True

        broad_terms = (
            "figure", "fig.", "diagram", "cycle", "transaction",
            "switching", "characteristics", "serial", "bus", "interface",
            "read", "write", "valid", "edge", "phase", "polarity",
            "建立时间", "保持时间", "访问时间", "上升沿", "下降沿", "采样",
        )
        if any(self._contains_keyword(text, term) for term in broad_terms):
            return True

        if self._image_block_bboxes(page):
            return True

        try:
            return len(page.get_drawings()) >= 8
        except Exception:
            return False

    def _matched_keywords(self, text: str) -> list[str]:
        return [
            keyword for keyword in self.TIMING_KEYWORDS
            if self._contains_keyword(text or "", keyword)
        ]

    def _classify_page_with_llm(self, page_text: str, page: fitz.Page) -> dict:
        cfg = self.figure_config
        if getattr(cfg, "llm_provider", "openai") != "openai":
            raise ValueError(f"不支持的 figures.llm_provider: {cfg.llm_provider}")

        client = self._get_llm_client()
        max_chars = int(getattr(cfg, "candidate_context_chars", 6000))
        text = (page_text or "")[:max_chars]
        layout_signals = {
            "image_blocks": len(self._image_block_bboxes(page)),
            "drawings": self._drawing_count(page),
            "heuristic_keywords": self._matched_keywords(page_text),
        }

        prompt = (
            "You are classifying pages from embedded chip datasheets. "
            "Decide whether this page is related to timing diagrams, bus waveforms, "
            "switching characteristics, setup/hold timing, clock/data validity windows, "
            "or signal transaction diagrams. Prefer recall, but reject ordinary block "
            "diagrams, pinouts, logos, and unrelated electrical tables.\n\n"
            f"Layout signals:\n{json.dumps(layout_signals, ensure_ascii=False)}\n\n"
            f"Page text:\n{text}"
        )

        response = client.chat.completions.create(
            model=getattr(cfg, "llm_model", "gpt-4.1"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Return only JSON. Be strict about timing-diagram relevance, "
                        "but include switching/timing parameter pages when they are "
                        "likely attached to waveforms."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "timing_page_detection",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "is_timing_diagram_related": {"type": "boolean"},
                            "confidence": {"type": "number"},
                            "reason": {"type": "string"},
                            "signals": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "suggested_caption": {"type": "string"},
                        },
                        "required": [
                            "is_timing_diagram_related",
                            "confidence",
                            "reason",
                            "signals",
                            "suggested_caption",
                        ],
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
            },
        )
        content = self._extract_llm_content(response)
        data = json.loads(content)
        confidence = float(data.get("confidence", 0.0))
        min_confidence = float(getattr(cfg, "min_confidence", 0.65))
        return {
            "save": bool(data.get("is_timing_diagram_related")) and confidence >= min_confidence,
            "method": getattr(cfg, "detection", "llm"),
            "confidence": confidence,
            "reason": str(data.get("reason", ""))[:500],
            "signals": data.get("signals", [])[:12],
            "suggested_caption": str(data.get("suggested_caption", ""))[:240],
        }

    def _extract_llm_content(self, response) -> str:
        if isinstance(response, str):
            return response
        if isinstance(response, dict):
            try:
                return response["choices"][0]["message"]["content"] or "{}"
            except (KeyError, IndexError, TypeError):
                return "{}"
        return response.choices[0].message.content or "{}"

    def _get_llm_client(self):
        if self._llm_client is not None:
            return self._llm_client

        cfg = self.figure_config
        api_key = getattr(cfg, "llm_api_key", "") or os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError(
                "figures.detection 使用 LLM 时需要配置 figures.llm_api_key "
                "或环境变量 OPENAI_API_KEY"
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError("需要安装 openai: pip install openai>=1.0.0") from exc

        base_url = getattr(cfg, "llm_base_url", "")
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._llm_client = OpenAI(**kwargs)
        return self._llm_client

    def _drawing_count(self, page: fitz.Page) -> int:
        try:
            return len(page.get_drawings())
        except Exception:
            return 0

    def _extract_caption(self, page_text: str) -> str:
        lines = [line.strip() for line in (page_text or "").splitlines() if line.strip()]
        figure_captions = []
        for line in lines:
            normalized = self._normalize_figure_label(line)
            if not normalized:
                continue
            figure_captions.append(normalized)
            if self._caption_has_domain_signal(normalized):
                return normalized[:240]
        if figure_captions:
            return " | ".join(figure_captions[:3])[:240]

        for line in lines:
            if any(
                self._contains_keyword(line, keyword)
                for keyword in self.TIMING_KEYWORDS
            ):
                return line[:240]
        return ""

    def _normalize_figure_label(self, line: str) -> str:
        text = re.sub(r"\s+", " ", line.strip())
        if not text:
            return ""

        # Normal Chinese figure labels.
        match = re.search(r"(图\s*\d+\s*[^。；;]{0,40})", text)
        if match:
            return match.group(1).strip()

        # Some embedded Chinese PDFs decode "图" as U+0CD2 or Kannada glyphs.
        match = re.search(r"[\u0cd2೒]\s*(\d{1,2})\s*([^。；;]{0,40})", text)
        if match:
            title = self._clean_decoded_text(match.group(2))
            return f"图{match.group(1)} {title}".strip()

        match = re.search(r"\b(fig(?:ure)?\.?\s*\d+\s*[^。；;]{0,40})", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        return ""

    def _caption_has_domain_signal(self, caption: str) -> bool:
        terms = (
            "时序", "ᯊ", "写", "ݭ", "读", "䇏", "ACK", "应答", "ᑨㄨ",
            "SCL", "SDA", "START", "STOP", "页写", "随机读", "顺序读",
            "ᄫ㡖", "乎ᑣ", "䱣ᴎ", "tSU", "tHD", "tWR",
        )
        return any(term in caption for term in terms)

    def _extract_semantic_hints(self, page_text: str) -> list[str]:
        text = page_text or ""
        hints = []
        checks = [
            ("I2C bus", ("I  C", "I2C", "I²C")),
            ("SCL clock line", ("SCL",)),
            ("SDA data line", ("SDA",)),
            ("ACK acknowledge", ("ACK", "ᑨㄨ", "应答")),
            ("NACK no acknowledge", ("NO ACK", "NACK", "非应答", "䴲ᑨㄨ")),
            ("START condition", ("START", "䍋ྟ", "起始")),
            ("STOP condition", ("STOP", "ذℶ", "停止")),
            ("byte write", ("字节写", "ᄫ㡖ݭ")),
            ("page write", ("页写", "图10页写")),
            ("ACK polling", ("ACK = 0", "ᑨㄨᶹ䆶", "应答查询")),
            ("current address read", ("当前地址读", "ᔧࠡ")),
            ("random read", ("随机读", "䱣ᴎ䇏")),
            ("sequential read", ("顺序读", "乎ᑣ䇏")),
            ("write cycle", ("tWR", "写周期", "ݭ਼ᳳ")),
            ("setup time", ("tSU", "setup")),
            ("hold time", ("tHD", "hold")),
        ]
        for label, needles in checks:
            if any(needle in text for needle in needles):
                hints.append(label)

        for label in self._extract_all_figure_labels(text):
            if label not in hints:
                hints.append(label)

        return hints[:16]

    def _extract_all_figure_labels(self, page_text: str) -> list[str]:
        labels = []
        for line in (page_text or "").splitlines():
            label = self._normalize_figure_label(line)
            if label and label not in labels:
                labels.append(label)
        return labels[:8]

    def _clean_decoded_text(self, text: str) -> str:
        return re.sub(r"[\x00-\x1f]+", " ", text).strip()

    def _contains_keyword(self, text: str, keyword: str) -> bool:
        if re.search(r"[\u4e00-\u9fff]", keyword):
            return keyword in text
        if re.search(r"[^A-Za-z0-9_ ]", keyword):
            return keyword.lower() in text.lower()
        return bool(re.search(rf"\b{re.escape(keyword)}\b", text, re.IGNORECASE))

    def _image_block_bboxes(self, page: fitz.Page) -> list[tuple[float, float, float, float]]:
        bboxes: list[tuple[float, float, float, float]] = []
        page_dict = page.get_text("dict")
        for block in page_dict.get("blocks", []):
            if block.get("type") != 1 or "bbox" not in block:
                continue
            x0, y0, x1, y1 = block["bbox"]
            width = x1 - x0
            height = y1 - y0
            if width < 120 or height < 80:
                continue
            if y1 < page.rect.height * 0.15 or y0 > page.rect.height * 0.92:
                continue
            bboxes.append((x0, y0, x1, y1))
        return bboxes

    def _render_page(self, page: fitz.Page, matrix: fitz.Matrix, output_path: Path, clip=None):
        pix = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)
        pix.save(str(output_path))

    def _merge(
        self,
        pages_text: list[dict],
        tables_by_page: dict[int, list[str]],
        figures_by_page: dict[int, list[dict]],
        bookmarks: list[dict],
    ) -> list[DocElement]:
        elements: list[DocElement] = []
        heading_stack: list[str] = []
        bookmark_map: dict[int, list[dict]] = {}
        for bm in bookmarks:
            bookmark_map.setdefault(bm["page"], []).append(bm)

        for page_info in pages_text:
            page_num = page_info["page"]
            text = page_info["text"]

            for bm in bookmark_map.get(page_num, []):
                self._update_heading_stack(heading_stack, bm["level"], bm["title"])
                elements.append(DocElement(
                    type="heading",
                    content=bm["title"],
                    context_chain=" > ".join(heading_stack),
                    level=bm["level"],
                    page=page_num,
                ))

            for table_md in tables_by_page.get(page_num, []):
                elements.append(DocElement(
                    type="table",
                    content=table_md,
                    context_chain=" > ".join(heading_stack),
                    page=page_num,
                    metadata={"row_count": table_md.count("\n")},
                ))

            for figure in figures_by_page.get(page_num, []):
                caption = figure.get("caption") or Path(figure["image_path"]).name
                elements.append(DocElement(
                    type="figure",
                    content=f"Timing diagram image: {caption}",
                    context_chain=" > ".join(heading_stack),
                    page=page_num,
                    metadata=figure,
                ))

            text_content = text.strip()
            if text_content:
                elements.append(DocElement(
                    type="text",
                    content=text_content,
                    context_chain=" > ".join(heading_stack),
                    page=page_num,
                ))

        return elements

    def _update_heading_stack(self, stack: list[str], level: int, title: str):
        while len(stack) >= level:
            stack.pop()
        stack.append(title)

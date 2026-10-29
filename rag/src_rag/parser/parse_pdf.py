"""Parse every PDF in the project root with docling and dump structured output."""
from __future__ import annotations

import json
import time
from pathlib import Path

from docling.document_converter import DocumentConverter

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = PROJECT_ROOT / "rag" / "data" / "raw"
OUT_DIR = PROJECT_ROOT / "rag" / "data" / "parsed"


def main() -> None:
    pdfs = sorted(RAW_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {RAW_DIR}")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    converter = DocumentConverter()

    for pdf in pdfs:
        print(f"Parsing: {pdf.name}")
        t0 = time.perf_counter()
        result = converter.convert(str(pdf))
        doc = result.document
        elapsed = time.perf_counter() - t0

        stem = pdf.stem
        md_path = OUT_DIR / f"{stem}.md"
        json_path = OUT_DIR / f"{stem}.json"
        text_path = OUT_DIR / f"{stem}.txt"

        md_path.write_text(doc.export_to_markdown(), encoding="utf-8")
        text_path.write_text(doc.export_to_text(), encoding="utf-8")
        json_path.write_text(
            json.dumps(doc.export_to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  done in {elapsed:.1f}s -> {md_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()

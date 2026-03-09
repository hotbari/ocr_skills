"""파이프라인 각 단계 산출물을 파일로 저장하는 유틸리티."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


class OutputSaver:
    """파이프라인 단계별 산출물을 output_dir에 JSON + Markdown으로 저장."""

    def __init__(self, output_dir: Path, document_id: str):
        self.output_dir = output_dir / document_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.document_id = document_id
        self.phase_times: dict[str, str] = {}

    # ── Phase 저장 메서드 ──────────────────────────────────────────────

    def save_phase0(self, stage0) -> None:
        """Stage 0: PDF 추출 결과 저장."""
        r = stage0.result
        data = {
            "phase": "stage0_extract",
            "timestamp": _now(),
            "duration_seconds": stage0.duration_seconds,
            "summary": {
                "page_count": r.page_count,
                "text_length": len(r.raw_text),
                "language": r.detected_language if isinstance(r.detected_language, str) else r.detected_language.value,
                "is_scanned": r.is_scanned,
                "scanned_pages": r.scanned_pages,
                "image_count": len(r.images),
                "table_count": len(r.tables),
            },
            "pages": [
                {
                    "page": p.page_number,
                    "word_count": p.word_count,
                    "text_preview": p.content[:300].replace("\n", " "),
                }
                for p in r.text_by_page
            ],
            "images": [
                {
                    "page": img.page_number,
                    "seq": img.sequence_in_page,
                    "path": img.image_path,
                    "size": f"{img.width}x{img.height}",
                }
                for img in r.images
            ],
            "tables": [
                {
                    "page": t.page_number,
                    "seq": t.sequence_in_page,
                    "markdown_preview": t.markdown[:200],
                }
                for t in r.tables
            ],
            "raw_text_preview": r.raw_text[:1000],
        }
        self._write_json("phase0_extract.json", data)
        self._write_text("phase0_raw_text.txt", r.raw_text)
        logger.info("Phase 0 산출물 저장 완료", path=str(self.output_dir / "phase0_extract.json"))

    def save_phase1(self, stage1) -> None:
        """Stage 1: 레이아웃 분석 결과 저장."""
        layout = stage1.layout
        pages_data = []
        for page_num, blocks in sorted(layout.blocks_by_page.items()):
            pages_data.append({
                "page": page_num,
                "block_count": len(blocks),
                "blocks": [
                    {
                        "seq": b.sequence_in_page,
                        "type": b.block_type if isinstance(b.block_type, str) else b.block_type.value,
                        "bbox": {"x0": round(b.bbox.x0), "y0": round(b.bbox.y0),
                                 "x1": round(b.bbox.x1), "y1": round(b.bbox.y1)},
                        "font_size": b.font_size,
                        "confidence": round(b.confidence, 3),
                        "text_preview": (b.text or "")[:150].replace("\n", " "),
                    }
                    for b in blocks
                ],
            })
        data = {
            "phase": "stage1_layout",
            "timestamp": _now(),
            "duration_seconds": stage1.duration_seconds,
            "summary": stage1.summary,
            "pages": pages_data,
        }
        self._write_json("phase1_layout.json", data)
        # 읽기 쉬운 텍스트 요약
        lines = [f"=== Stage 1: 레이아웃 분석 ({stage1.duration_seconds:.2f}s) ===\n"]
        for p in pages_data:
            lines.append(f"\n[Page {p['page']}] 블록 {p['block_count']}개")
            for b in p["blocks"]:
                lines.append(f"  [{b['type'].upper():15s}] fs={b['font_size'] or '?':>5}  {b['text_preview'][:80]}")
        self._write_text("phase1_layout.txt", "\n".join(lines))
        logger.info("Phase 1 산출물 저장 완료", path=str(self.output_dir / "phase1_layout.json"))

    def save_phase2(self, stage2) -> None:
        """Stage 2: 구조화 결과 저장."""
        toc_data = [
            {
                "level": n.level,
                "title": n.title,
                "page_start": n.page_start,
                "page_end": n.page_end,
                "sequence": n.sequence_number,
            }
            for n in stage2.toc.nodes
        ]
        sections_data = [
            {
                "seq": s.sequence_number,
                "level": s.heading_level,
                "heading": s.heading,
                "page_start": s.page_start,
                "page_end": s.page_end,
                "content_length": len(s.content),
                "content_preview": s.content[:500].replace("\n", " "),
            }
            for s in stage2.sections
        ]
        tables_data = [
            {
                "page": t.page_number,
                "seq": t.sequence_in_page,
                "caption": t.caption,
                "markdown": t.markdown,
            }
            for t in stage2.tables
        ]
        images_data = [
            {
                "page": img.page_number,
                "seq": img.sequence_in_page,
                "caption": img.caption,
                "path": img.image_path,
            }
            for img in stage2.images
        ]
        data = {
            "phase": "stage2_structure",
            "timestamp": _now(),
            "duration_seconds": stage2.duration_seconds,
            "summary": stage2.summary,
            "toc": toc_data,
            "sections": sections_data,
            "tables": tables_data,
            "images": images_data,
        }
        self._write_json("phase2_structure.json", data)
        # Markdown 리포트
        self._write_text("phase2_toc.md", self._build_toc_md(toc_data))
        self._write_text("phase2_sections.md", self._build_sections_md(stage2.sections, stage2.tables))
        logger.info("Phase 2 산출물 저장 완료", path=str(self.output_dir / "phase2_structure.json"))

    def save_phase3(self, stage3) -> None:
        """Stage 3: 이미지 캡셔닝 결과 저장."""
        data = {
            "phase": "stage3_vision",
            "timestamp": _now(),
            "duration_seconds": stage3.duration_seconds,
            "summary": stage3.summary,
            "images": [
                {
                    "page": img.page_number,
                    "seq": img.sequence_in_page,
                    "caption": img.caption,
                    "vision_description": img.vision_description,
                    "processed": img.vision_processed,
                }
                for img in stage3.images
            ],
        }
        self._write_json("phase3_vision.json", data)
        logger.info("Phase 3 산출물 저장 완료")

    def save_phase4(self, stage4) -> None:
        """Stage 4: 태그/요약 결과 저장."""
        data = {
            "phase": "stage4_tags",
            "timestamp": _now(),
            "duration_seconds": stage4.duration_seconds,
            "summary": stage4.summary,
            "sections": [
                {
                    "heading": s.heading,
                    "tags": s.tags,
                    "summary": s.summary,
                }
                for s in stage4.sections
            ],
        }
        self._write_json("phase4_tags.json", data)
        logger.info("Phase 4 산출물 저장 완료")

    def save_final_report(self, stage0, stage1, stage2, pipeline_state) -> None:
        """최종 종합 리포트 저장 (JSON + Markdown)."""
        report = {
            "document_id": self.document_id,
            "generated_at": _now(),
            "pipeline_result": {
                "status": "completed",
                "total_duration_seconds": pipeline_state.total_duration_seconds,
                "stages": {
                    name: {
                        "status": r.status if isinstance(r.status, str) else r.status.value,
                        "duration_seconds": r.duration_seconds,
                        "error": r.error_message,
                    }
                    for name, r in pipeline_state.stages.items()
                },
            },
            "document_info": {
                "page_count": stage0.result.page_count,
                "language": stage0.result.detected_language if isinstance(stage0.result.detected_language, str) else stage0.result.detected_language.value,
                "is_scanned": stage0.result.is_scanned,
                "text_length": len(stage0.result.raw_text),
            },
            "extraction_stats": {
                "total_blocks": stage1.layout.total_blocks,
                "block_type_counts": stage1.summary.get("block_type_counts", {}),
                "sections": len(stage2.sections),
                "toc_nodes": len(stage2.toc.nodes),
                "tables": len(stage2.tables),
                "images": len(stage2.images),
            },
        }
        self._write_json("final_report.json", report)
        # Markdown 최종 리포트
        md = self._build_final_md(report, stage2)
        self._write_text("final_report.md", md)
        logger.info("최종 리포트 저장 완료", path=str(self.output_dir / "final_report.md"))

    # ── Markdown 빌더 ─────────────────────────────────────────────────

    def _build_toc_md(self, toc_data: list[dict]) -> str:
        lines = ["# 목차 (TOC)\n"]
        for node in toc_data:
            indent = "  " * (node["level"] - 1)
            lines.append(f"{indent}- **[L{node['level']}]** {node['title']} (p.{node['page_start']})")
        return "\n".join(lines)

    def _build_sections_md(self, sections, tables) -> str:
        table_by_section: dict[str, list] = {}
        for t in tables:
            sid = t.section_id or "__no_section__"
            table_by_section.setdefault(sid, []).append(t)

        lines = ["# 섹션 내용\n"]
        for s in sections:
            prefix = "#" * min(s.heading_level + 1, 6)
            lines.append(f"\n{prefix} {s.heading or '(제목 없음)'}")
            lines.append(f"*페이지: {s.page_start}~{s.page_end}*\n")
            if s.content:
                lines.append(s.content)
            for t in table_by_section.get(s.id, []):
                if t.caption:
                    lines.append(f"\n**{t.caption}**")
                if t.markdown:
                    lines.append(f"\n{t.markdown}")
        return "\n".join(lines)

    def _build_final_md(self, report: dict, stage2) -> str:
        stats = report["extraction_stats"]
        doc = report["document_info"]
        dur = report["pipeline_result"]["total_duration_seconds"] or 0
        lines = [
            f"# OCR 파이프라인 최종 리포트",
            f"\n생성일시: {report['generated_at']}",
            f"\n## 문서 정보",
            f"- 페이지 수: {doc['page_count']}",
            f"- 언어: {doc['language']}",
            f"- 스캔 여부: {doc['is_scanned']}",
            f"- 텍스트 길이: {doc['text_length']:,}자",
            f"\n## 파이프라인 결과",
            f"- 총 소요시간: {dur:.1f}초",
        ]
        for name, s in report["pipeline_result"]["stages"].items():
            dur_s = f"{s['duration_seconds']:.2f}s" if s["duration_seconds"] else "-"
            lines.append(f"- {name}: {s['status']} ({dur_s})")

        lines += [
            f"\n## 추출 통계",
            f"- 레이아웃 블록: {stats['total_blocks']}개",
            f"- 섹션: {stats['sections']}개",
            f"- TOC 노드: {stats['toc_nodes']}개",
            f"- 테이블: {stats['tables']}개",
            f"- 이미지: {stats['images']}개",
            f"\n## 블록 타입별 분포",
        ]
        for btype, cnt in sorted(stats["block_type_counts"].items(), key=lambda x: -x[1]):
            lines.append(f"- {btype}: {cnt}개")

        lines.append("\n## 목차 (TOC)\n")
        for node in stage2.toc.nodes:
            indent = "  " * (node.level - 1)
            lines.append(f"{indent}- [L{node.level}] {node.title} (p.{node.page_start})")

        lines.append("\n## 테이블 목록\n")
        for i, t in enumerate(stage2.tables, 1):
            lines.append(f"### 테이블 {i} (p.{t.page_number})")
            if t.caption:
                lines.append(f"**캡션**: {t.caption}\n")
            if t.markdown:
                lines.append(t.markdown)
            lines.append("")

        return "\n".join(lines)

    # ── 파일 IO ───────────────────────────────────────────────────────

    def _write_json(self, filename: str, data: Any) -> None:
        path = self.output_dir / filename
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_text(self, filename: str, content: str) -> None:
        path = self.output_dir / filename
        path.write_text(content, encoding="utf-8")

    def list_outputs(self) -> list[str]:
        return sorted(str(p.relative_to(self.output_dir.parent.parent)) for p in self.output_dir.rglob("*") if p.is_file())


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

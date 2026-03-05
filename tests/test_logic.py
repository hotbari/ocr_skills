"""핵심 로직 단위 테스트 (외부 서비스 불필요)."""
import sys
sys.path.insert(0, ".")

from src.core.models import BlockType, BoundingBox, LayoutBlock
from src.pipeline.stage2_structure import StructureBuilder

DOC_ID = "test-doc-001"


def make_block(block_type, text, page, y0=0):
    return LayoutBlock(
        document_id=DOC_ID,
        page_number=page,
        block_type=block_type,
        bbox=BoundingBox(x0=0, y0=y0, x1=500, y1=y0 + 20),
        text=text,
        sequence_in_page=0,
    )


def test_structure_and_toc():
    builder = StructureBuilder(DOC_ID)

    blocks = [
        make_block(BlockType.TITLE, "제1장 서론", 1, y0=50),
        make_block(BlockType.TEXT, "딥러닝은 인공신경망 기반의 머신러닝 분야입니다.", 1, y0=80),
        make_block(BlockType.TEXT, "여러 은닉층을 통해 복잡한 패턴을 학습합니다.", 1, y0=110),
        make_block(BlockType.TITLE, "1.1 배경 및 동기", 1, y0=150),
        make_block(BlockType.TEXT, "기존 머신러닝의 한계를 극복하기 위해 개발되었습니다.", 2, y0=20),
        make_block(BlockType.TABLE, "", 2, y0=60),
        make_block(BlockType.TABLE_CAPTION, "표 1.1 주요 모델 비교", 2, y0=90),
        make_block(BlockType.TITLE, "제2장 방법론", 3, y0=30),
        make_block(BlockType.TEXT, "본 연구에서 사용한 방법론을 설명합니다.", 3, y0=60),
        make_block(BlockType.FIGURE, "", 3, y0=100),
        make_block(BlockType.FIGURE_CAPTION, "그림 2.1 시스템 구조도", 3, y0=130),
        make_block(BlockType.TITLE, "2.1 데이터 전처리", 4, y0=20),
        make_block(BlockType.TEXT, "데이터 정제 및 정규화 과정을 수행합니다.", 4, y0=50),
    ]

    for block in blocks:
        builder.process_block(block)

    builder.merge_stage0_tables([])
    builder.merge_stage0_images([])

    sections = builder.finalize_sections()
    toc = builder.build_toc()

    print("=== 섹션 구조 ===")
    for s in sections:
        indent = "  " * (s.heading_level - 1) if s.heading else ""
        heading = s.heading or "(제목 없음)"
        print(f"  {indent}[L{s.heading_level}] {heading} | 내용 {len(s.content)}자 | 엔티티 {len(s.entity_ids)}개")

    print()
    print("=== TOC 계층 구조 ===")

    def print_toc(nodes, node_id, depth=0):
        node = next((n for n in nodes if n.id == node_id), None)
        if not node:
            return
        caption = repr(node.title)
        print(f"  {'  ' * depth}[L{node.level}] {node.title} (p.{node.page_start}) entities={len(node.entity_ids)}")
        for child_id in node.children_ids:
            print_toc(nodes, child_id, depth + 1)

    root_nodes = [n for n in toc.nodes if n.parent_id is None]
    for root in root_nodes:
        print_toc(toc.nodes, root.id)

    print()
    print(f"TOC 통계: L1={toc.total_l1}, L2={toc.total_l2}, L3={toc.total_l3}")
    print(f"테이블: {len(builder.tables)}개")
    print(f"이미지: {len(builder.images)}개")

    print()
    print("=== 엔티티 캡션 확인 ===")
    for t in builder.tables:
        print(f"  테이블 page={t.page_number} caption={t.caption}")
    for img in builder.images:
        print(f"  이미지 page={img.page_number} caption={img.caption}")

    print()
    print("=== TOC ↔ Section 연결 확인 ===")
    for node in toc.nodes:
        section = next((s for s in sections if s.id == node.section_id), None)
        toc_back = section.toc_node_id == node.id if section else False
        status = "OK" if (section and toc_back) else "FAIL"
        print(f"  [{status}] TOC[{node.title}] → section={section is not None}, back_ref={toc_back}")

    # 검증
    assert len(sections) == 4, f"섹션 4개 예상, 실제 {len(sections)}"
    assert toc.total_l1 == 2, f"L1 2개 예상, 실제 {toc.total_l1}"
    assert toc.total_l2 == 2, f"L2 2개 예상, 실제 {toc.total_l2}"
    assert len(builder.tables) == 1, f"테이블 1개 예상, 실제 {len(builder.tables)}"
    assert len(builder.images) == 1, f"이미지 1개 예상, 실제 {len(builder.images)}"
    assert builder.tables[0].caption == "표 1.1 주요 모델 비교", "테이블 캡션 불일치"
    assert builder.images[0].caption == "그림 2.1 시스템 구조도", "이미지 캡션 불일치"

    # TOC ↔ Section 양방향 연결 검증
    for node in toc.nodes:
        section = next((s for s in sections if s.id == node.section_id), None)
        assert section is not None, f"TOC 노드 {node.title}에 연결된 섹션 없음"
        assert section.toc_node_id == node.id, f"Section의 toc_node_id 역참조 불일치"

    # 부모-자식 관계 검증
    l1_nodes = [n for n in toc.nodes if n.level == 1]
    l2_nodes = [n for n in toc.nodes if n.level == 2]
    for l2 in l2_nodes:
        assert l2.parent_id is not None, f"L2 노드 {l2.title}에 부모 없음"
        parent = next((n for n in l1_nodes if n.id == l2.parent_id), None)
        assert parent is not None, f"L2 노드 {l2.title}의 부모가 L1이 아님"
        assert l2.id in parent.children_ids, "부모의 children_ids에 자식 없음"

    print()
    print("모든 검증 통과")


def test_heading_level_inference():
    """헤딩 레벨 추정 테스트."""
    from src.pipeline.stage2_structure import StructureBuilder
    builder = StructureBuilder(DOC_ID)
    bbox = BoundingBox(x0=0, y0=50, x1=500, y1=70)

    cases = [
        ("제1장 서론", 1),
        ("Chapter 1 Introduction", 1),
        ("1.1 배경", 2),
        ("2.3 실험 결과", 2),
        ("1.1.1 세부 항목", 3),
        ("결론", 1),
    ]

    print()
    print("=== 헤딩 레벨 추정 ===")
    for text, expected in cases:
        level = builder._infer_heading_level(text, bbox)
        status = "OK" if level == expected else f"FAIL (expected {expected})"
        print(f"  [{status}] {repr(text)} → L{level}")

    print()
    print("헤딩 레벨 추정 완료")


if __name__ == "__main__":
    test_structure_and_toc()
    test_heading_level_inference()

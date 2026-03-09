"""OCR Result (PRD 형식) API 라우터."""

from fastapi import APIRouter, HTTPException, status

from src.core.ocr_result import OCRResult, OCRResultPage
from src.db.repositories.ocr_result_repo import OCRResultRepository

router = APIRouter(prefix="/ocr-results", tags=["ocr-results"])


def _repo() -> OCRResultRepository:
    return OCRResultRepository()


@router.get("", summary="OCR 결과 목록")
async def list_ocr_results(page: int = 1, page_size: int = 20):
    results, total = await _repo().list_all(page=page, page_size=page_size)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "ocr_result_id": r.ocr_result_id,
                "ref_document_id": r.ref_document_id,
                "created_at": r.created_at,
                "total_pages": 0,   # 목록에선 page 필드 미로드
            }
            for r in results
        ],
    }


@router.get("/{document_id}", response_model=OCRResult, summary="OCR 결과 전체 조회")
async def get_ocr_result(document_id: str):
    result = await _repo().get_by_document(document_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OCR 결과 없음")
    return result


@router.get("/{document_id}/pages/{page_num}", response_model=OCRResultPage, summary="특정 페이지 조회")
async def get_ocr_result_page(document_id: str, page_num: int):
    result = await _repo().get_by_document(document_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OCR 결과 없음")
    for p in result.page:
        if p.page_num == page_num:
            return p
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"페이지 {page_num} 없음")


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, summary="OCR 결과 삭제")
async def delete_ocr_result(document_id: str):
    await _repo().delete(document_id)

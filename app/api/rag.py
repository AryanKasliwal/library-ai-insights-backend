from fastapi import APIRouter
from pydantic import BaseModel
from app.services.rag_service import rag_service
from app.services.utils import normalize_to_filename
import os

router = APIRouter()

class QueryRequest(BaseModel):
    bookId: str  # This is title from frontend
    question: str

@router.post("/query")
def rag_query(payload: QueryRequest):

    normalized_name = normalize_to_filename(payload.bookId)
    pdf_path = f"app/data/pdfs/{normalized_name}.pdf"

    if not os.path.exists(pdf_path):
        return {"error": f"PDF not found for {payload.bookId}"}

    results = rag_service.query(normalized_name, payload.question)

    if results is None:
        return {"error": "Index not built yet"}

    return {
        "answer": results[0],
        "sources": [
            {"text": r, "page": None} for r in results
        ]
    }

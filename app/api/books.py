from fastapi import APIRouter, Query
from app.services.metadata_service import metadata_service

router = APIRouter()

@router.get("")
def search_books(query: str = Query(None)):
    if query:
        return metadata_service.search_books(query)
    return metadata_service.df.head(50).to_dict(orient="records")

@router.get("/{book_id}")
def get_book(book_id: str):
    return metadata_service.get_book(book_id)

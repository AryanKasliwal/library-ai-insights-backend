from fastapi import APIRouter, Request
from pydantic import BaseModel
from app.services.rag_service import rag_service
from app.services.rag_service_hf import rag_service_hf
from app.services.utils import normalize_to_filename
import os
import random


router = APIRouter()

# New endpoint: List books available for AI chat
@router.get("/chat-books")
def list_chat_books():
    print("Received request to list chat books")
    vector_store_path = "vector_store"
    index_files = [f for f in os.listdir(vector_store_path) if f.endswith('.index')]
    # Remove leading underscores and file extension, replace underscores with spaces
    book_names = []
    for fname in index_files:
        name = fname.replace('.index', '')
        # Remove leading underscores (if any)
        name = name.lstrip('_')
        # Replace underscores with spaces
        name = name.replace('_', ' ')
        book_names.append(name)
    return {"books": book_names}

class QueryRequest(BaseModel):
    bookId: str  # This is title from frontend
    question: str


# In-memory chat history: {session_id: {book_id: [messages]}}
chat_histories = {}

class ChatMessage(BaseModel):
    book_name: str
    message: str

# Helper to get session id (for demo: from headers or fallback to IP)
def get_session_id(request: Request):
    sid = request.headers.get("X-Session-Id")
    if sid:
        return sid
    # fallback: use client host (not secure, demo only)
    return request.client.host


# Chat logic only (no endpoints)
from app.services.rag_service import rag_service
from app.services.utils import normalize_to_filename

def store_and_reply(session_id: str, book_name: str, msg: str):
    normalized_book = normalize_to_filename(book_name)

    if session_id not in chat_histories:
        chat_histories[session_id] = {}
    if normalized_book not in chat_histories[session_id]:
        chat_histories[session_id][normalized_book] = []

    history = chat_histories[session_id][normalized_book]
    history.append({"role": "user", "message": msg})

    # Call RAG with chat history
    # result = rag_service.query(normalized_book, msg, chat_history=history)
    result = rag_service_hf.query(normalized_book, msg, chat_history=history)

    history.append({
        "role": "bot", 
        "message": result["answer"],
        "sources": result["sources"]
    })

    return result["answer"], result["sources"], history

def get_chat_from_history(session_id: str, book_name: str):
    normalized_book = normalize_to_filename(book_name)
    history = chat_histories.get(session_id, {}).get(normalized_book, [])
    return history

def clear_history(session_id: str):
    chat_histories.pop(session_id, None)

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

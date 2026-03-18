"""Book API endpoints for the library system.

Endpoints:
- GET /api/books/{isbn} - Get book details
- GET /api/books/{isbn}/similar - Get similar books with recommendations
- GET /api/books/search - Search books by title/author/category
- GET /api/stats - Get system statistics
"""

from fastapi import APIRouter, Query, HTTPException, Request
from fastapi.responses import FileResponse
from typing import List, Optional, Dict
from pydantic import BaseModel
from app.api.rag import ChatMessage, get_session_id, store_and_reply, clear_history, get_chat_from_history
import os
import glob
import difflib
import boto3
from botocore.exceptions import ClientError
from app.services.book_store import BookStore
from app.services.utils import normalize_to_filename
from app.services.cache_manager import register_file

router = APIRouter(tags=["books"])

S3_BUCKET = os.environ.get("S3_BUCKET")
S3_PREFIX = os.environ.get("S3_PDF_PREFIX", "pdfs/")
PDF_DIR = "app/data/pdfs"


def _get_s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )
@router.get("/pdf/{book_name}")
def serve_pdf(book_name: str):
    """Serve PDF file, downloading from S3 on demand if not cached locally."""
    book_saved_name = normalize_to_filename(book_name)
    pdf_path = f"{PDF_DIR}/{book_saved_name}.pdf"

    if not os.path.exists(pdf_path):
        matches = glob.glob(f"{PDF_DIR}/{book_saved_name}*.pdf")
        if matches:
            pdf_path = matches[0]
        else:
            os.makedirs(PDF_DIR, exist_ok=True)
            s3 = _get_s3_client()
            s3_key = f"pdfs/{book_saved_name}.pdf"
            try:
                print(f"⬇️ Downloading PDF {s3_key} from S3...")
                s3.download_file(S3_BUCKET, s3_key, pdf_path)
                print(f"✅ PDF downloaded: {book_saved_name}")
                register_file(pdf_path)  # register for cache expiry
            except Exception as e:
                print(f"❌ PDF download failed for {s3_key}: {e}")
                raise HTTPException(
                    status_code=404,
                    detail=f"PDF not found for '{book_name}': {e}"
                )

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={book_saved_name}.pdf"}
    )


@router.get("/pdf-url/{book_key}")
def get_pdf_url(book_key: str):
    """Returns a presigned S3 URL for the book PDF."""
    s3 = _get_s3_client()
    s3_key = f"{S3_PREFIX}{book_key}.pdf"

    try:
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": s3_key},
            ExpiresIn=3600
        )
        return {"url": url}
    except ClientError as e:
        return {"url": None, "error": str(e)}


# ============= Chat Endpoints =============

@router.post("/chat")
async def chat_endpoint(payload: ChatMessage, request: Request):
    session_id = get_session_id(request)
    bot_reply, sources, history = store_and_reply(session_id, payload.book_name, payload.message)
    return {
        "status": "ok",
        "reply": bot_reply,
        "sources": sources,
        "history": history
    }


@router.post("/chat/clear")
async def clear_chat_history(request: Request):
    session_id = get_session_id(request)
    clear_history(session_id)
    return {"status": "cleared"}


_store: Optional[BookStore] = None


@router.get("/chat/history")
async def get_chat_history(book_name: str, request: Request):
    session_id = get_session_id(request)
    return {"history": get_chat_from_history(session_id, book_name)}


# ============= Pagination & Search Helpers =============

def _paginate_results(results: List[Dict], page: int = 1, limit: int = 10) -> Dict:
    """Paginate results and return with metadata."""
    total = len(results)
    total_pages = max(1, (total + limit - 1) // limit)
    page = max(1, page)
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    paginated = results[start_idx:end_idx]
    return {
        'results': paginated,
        'pagination': {
            'page': page,
            'limit': limit,
            'total': total,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_prev': page > 1,
        }
    }


def _safe_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _detect_search_type(query: str, store: BookStore) -> str:
    """Auto-detect search type (title, author, or category).

    Uses heuristics to guess the most likely search type.
    Returns: 'title', 'author', or 'category'
    """
    author_results = store.search_by_author(query)
    if author_results:
        return 'author'

    category_results = store.search_by_category(query)
    if category_results:
        return 'category'

    return 'title'


def _smart_search(query: str, store: BookStore) -> List[Dict]:
    """Perform smart search across title, author, and category.

    Combines results from all search types and deduplicates by ISBN.
    """
    seen_isbns = {}
    results = []

    author_results = store.search_by_author(query)
    for book in author_results:
        isbn = book.get('isbn13') or book.get('isbn10')
        if isbn and isbn not in seen_isbns:
            seen_isbns[isbn] = True
            results.append(book)

    _, category_results = _resolve_category_query(query, store)
    for book in category_results:
        isbn = book.get('isbn13') or book.get('isbn10')
        if isbn and isbn not in seen_isbns:
            seen_isbns[isbn] = True
            results.append(book)

    title_results = store.search_by_title(query)
    for book in title_results:
        isbn = book.get('isbn13') or book.get('isbn10')
        if isbn and isbn not in seen_isbns:
            seen_isbns[isbn] = True
            results.append(book)

    results.sort(
        key=lambda b: (float(b.get('average_rating', 0)), int(b.get('ratings_count', 0))),
        reverse=True
    )
    return results


def _resolve_category_query(category_query: str, store: BookStore):
    """Resolve category query with typo tolerance.

    Returns tuple: (resolved_category, results)
    """
    exact_results = store.search_by_category(category_query)
    if exact_results:
        return category_query, exact_results

    category_index = store.indexes.get('by_category', {})
    category_keys = list(category_index.keys())
    if not category_keys:
        return category_query, []

    query_lower = category_query.lower().strip()
    best_match = difflib.get_close_matches(query_lower, category_keys, n=1, cutoff=0.72)
    if not best_match:
        return category_query, []

    matched_category = best_match[0]
    return matched_category, store.search_by_category(matched_category)


def init_book_store(csv_path: str = "app/data/csv/enriched_books.csv",
                    recommendations_path: str = "app/services/book_recommendations.json"):
    """Initialize global book store at application startup."""
    global _store
    print("\n📚 Initializing BookStore...")
    _store = BookStore(csv_path, recommendations_path)


def get_store() -> BookStore:
    """Get the global book store."""
    if _store is None:
        raise RuntimeError("BookStore not initialized. Call init_book_store() at app startup.")
    return _store


# ============= Response Models =============

class BookResponse:
    """Book data for API response."""

    @staticmethod
    def from_dict(book_dict):
        if not book_dict:
            return None
        return {
            'found': True,
            'id': book_dict.get('isbn13') or book_dict.get('isbn10'),
            'isbn13': book_dict.get('isbn13', ''),
            'isbn10': book_dict.get('isbn10', ''),
            'title': book_dict.get('title', ''),
            'author': book_dict.get('authors', ''),
            'publisher': book_dict.get('publisher', ''),
            'year': _safe_int(book_dict.get('published_year')),
            'year_str': book_dict.get('published_year', ''),
            'description': book_dict.get('description', ''),
            'subjects': [s.strip() for s in book_dict.get('categories', '').split(',') if s.strip()],
            'rating': float(book_dict.get('average_rating', 0)),
            'ratingsCount': int(book_dict.get('ratings_count', 0)),
            'pages': book_dict.get('num_pages', ''),
            'language': book_dict.get('language_code', ''),
            'thumbnail': book_dict.get('thumbnail_m', ''),
            'thumbnails': {
                'small': book_dict.get('thumbnail_s', ''),
                'medium': book_dict.get('thumbnail_m', ''),
                'large': book_dict.get('thumbnail_l', ''),
            },
            'available': True,   # TODO: Check from library inventory
            'location': None,    # TODO: Get from library system
            'callNumber': None,  # TODO: Get from library system
        }


# ============= API Endpoints =============

@router.get("/chat-books")
def list_chat_books():
    import json
    import random

    def stable_shuffle(books):
        rng = random.Random(42)  # fixed seed = always same order
        shuffled = books.copy()
        rng.shuffle(shuffled)
        return shuffled

    book_list_path = "book_list.json"
    if os.path.exists(book_list_path):
        with open(book_list_path, "r") as f:
            data = json.load(f)
            return {"books": stable_shuffle(data.get("books", []))}

    # Fallback: scan vector_store
    vector_store_path = "vector_store"
    if not os.path.exists(vector_store_path):
        return {"books": []}
    index_files = [f for f in os.listdir(vector_store_path) if f.endswith('.index')]
    book_names = []
    for fname in index_files:
        name = fname.replace('.index', '')
        name = name.lstrip('_')
        name = name.replace('_', ' ')
        if name.startswith('. '):
            name = name[2:]
        book_names.append(name)
    return {"books": stable_shuffle(book_names)}


@router.get("/search")
def smart_search(
    q: Optional[str] = Query(None, description="Search query (title, author, category, or general)"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(10, ge=1, le=100, description="Results per page"),
    year: Optional[int] = Query(None, description="Filter by published year"),
    book_type: Optional[str] = Query(None, description="Filter by book type (Article, Journal, Book)"),
    genre: Optional[str] = Query(None, description="Filter by genre/category"),
):
    """Smart search across all book data (title, author, category).

    Auto-detects search type and combines results, then paginates.
    Returns top 10 results per page by rating.

    Example: GET /api/books/search?q=python&page=1&limit=10
    """
    store = get_store()
    query = (q or "").strip()

    def _apply_filters(books):
        filtered = books
        if year is not None:
            filtered = [b for b in filtered if str(b.get('published_year', '')) == str(year)]
        if book_type is not None:
            filtered = [b for b in filtered if b.get('type', '').lower() == book_type.lower()]
        if genre is not None:
            filtered = [b for b in filtered if genre.lower() in (b.get('categories', '') or '').lower()]
        return filtered

    if not query:
        unique_books = {}
        for book in store.books_by_isbn.values():
            isbn = book.get('isbn13') or book.get('isbn10')
            if not isbn or isbn in unique_books:
                continue
            unique_books[isbn] = book

        all_results = list(unique_books.values())
        all_results.sort(
            key=lambda b: (_safe_int(b.get('published_year')) or 0),
            reverse=True,
        )

        filtered_results = _apply_filters(all_results)
        book_responses = [BookResponse.from_dict(b) for b in filtered_results]
        paginated = _paginate_results(book_responses, page=page, limit=limit)

        return {
            'query': None,
            'search_type': 'recent',
            'resolved_category': None,
            'category_correction_applied': False,
            'results': paginated['results'],
            'pagination': paginated['pagination'],
        }

    exact_category_results = store.search_by_category(query)
    resolved_category, resolved_category_results = _resolve_category_query(query, store)
    category_correction_applied = (
        not exact_category_results
        and bool(resolved_category_results)
        and resolved_category.lower() != query.lower().strip()
    )

    all_results = _smart_search(query, store)
    filtered_results = _apply_filters(all_results)
    book_responses = [BookResponse.from_dict(b) for b in filtered_results]
    paginated = _paginate_results(book_responses, page=page, limit=limit)

    return {
        'query': query,
        'search_type': 'smart',
        'resolved_category': resolved_category if category_correction_applied else None,
        'category_correction_applied': category_correction_applied,
        'results': paginated['results'],
        'pagination': paginated['pagination'],
    }


@router.get("/{isbn}")
def get_book(isbn: str):
    """Get a single book by ISBN.

    Example: GET /api/books/9780439785969
    """
    try:
        store = get_store()
        print(f"✓ Store retrieved: {store is not None}, Books: {len(store.books_by_isbn)}")
        book = store.get_book(isbn)
        print(f"  Looking for ISBN {isbn}: {book is not None}")
        if book:
            print(f"  Found: {book['title'][:30]}")

        if not book:
            return {
                'found': False,
                'isbn': isbn,
                'message': f"Book not found: {isbn}",
            }

        resp = BookResponse.from_dict(book)
        if isinstance(resp, dict):
            resp['found'] = True
        return resp
    except Exception as e:
        print(f"❌ Error in get_book: {e}")
        raise


@router.get("/{isbn}/similar")
def get_similar_books(isbn: str, limit: int = Query(100, ge=1, le=100)):
    """Get similar books for a given ISBN.

    Uses Jaccard similarity on categories + rating quality boost.

    Example: GET /api/books/9780439785969/similar?limit=100
    """
    store = get_store()
    book = store.get_book(isbn)

    if not book:
        return {
            'found': False,
            'isbn': isbn,
            'message': f"Book not found: {isbn}",
            'book': None,
            'similar_books': [],
            'total_similar': 0,
        }

    target_response = BookResponse.from_dict(book)
    if isinstance(target_response, dict):
        target_response['found'] = True

    similar_books = store.get_similar_books(isbn, limit=limit)
    similar_response = [
        {
            'book': BookResponse.from_dict(item['book']),
            'similarity_score': item['similarity_score'],
        }
        for item in similar_books
    ]

    return {
        'book': target_response,
        'similar_books': similar_response,
        'total_similar': len(similar_response),
    }


@router.get("/search/title")
def search_by_title(
    q: str = Query(..., min_length=1, description="Title search query"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(10, ge=1, le=100, description="Results per page"),
):
    """Search books by title with pagination.

    Example: GET /api/books/search/title?q=Harry+Potter&page=1&limit=10
    """
    store = get_store()
    all_results = store.search_by_title(q)
    book_responses = [BookResponse.from_dict(b) for b in all_results]
    paginated = _paginate_results(book_responses, page=page, limit=limit)

    return {
        'query': q,
        'search_type': 'title',
        'results': paginated['results'],
        'pagination': paginated['pagination'],
    }


@router.get("/search/author")
def search_by_author(
    q: str = Query(..., min_length=1, description="Author search query"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(10, ge=1, le=100, description="Results per page"),
):
    """Search books by author with pagination.

    Example: GET /api/books/search/author?q=J.K.+Rowling&page=1&limit=10
    """
    store = get_store()
    all_results = store.search_by_author(q)
    book_responses = [BookResponse.from_dict(b) for b in all_results]
    paginated = _paginate_results(book_responses, page=page, limit=limit)

    return {
        'query': q,
        'search_type': 'author',
        'results': paginated['results'],
        'pagination': paginated['pagination'],
    }


@router.get("/search/category")
def search_by_category(
    category: str = Query(..., min_length=1, description="Category search query"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(10, ge=1, le=100, description="Results per page"),
):
    """Search books by category with pagination.

    Example: GET /api/books/search/category?category=Fiction&page=1&limit=10
    """
    store = get_store()
    resolved_category, all_results = _resolve_category_query(category, store)

    all_results.sort(
        key=lambda b: (float(b.get('average_rating', 0)), int(b.get('ratings_count', 0))),
        reverse=True,
    )

    book_responses = [BookResponse.from_dict(b) for b in all_results]
    paginated = _paginate_results(book_responses, page=page, limit=limit)

    return {
        'category': category,
        'resolved_category': resolved_category,
        'search_type': 'category',
        'results': paginated['results'],
        'pagination': paginated['pagination'],
    }


@router.get("/trending")
def get_trending(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(10, ge=1, le=100, description="Results per page"),
):
    """Get trending books (highest rated with most reviews) with pagination.

    Example: GET /api/books/trending?page=1&limit=10
    """
    store = get_store()
    all_results = store.get_top_rated_books(limit=500)
    book_responses = [BookResponse.from_dict(b) for b in all_results]
    paginated = _paginate_results(book_responses, page=page, limit=limit)

    return {
        'search_type': 'trending',
        'results': paginated['results'],
        'pagination': paginated['pagination'],
    }


@router.get("/stats")
def get_stats():
    """Get BookStore statistics.

    Example: GET /api/books/stats
    """
    store = get_store()
    return store.get_stats()


# ============= Export for main app =============

__all__ = ['router', 'init_book_store', 'get_store']
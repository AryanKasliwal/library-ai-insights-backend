"""Book API endpoints for the library system.

Endpoints:
- GET /api/books/{isbn} - Get book details
- GET /api/books/{isbn}/similar - Get similar books with recommendations
- GET /api/books/search - Search books by title/author/category
- GET /api/stats - Get system statistics
"""

from fastapi import APIRouter, Query, HTTPException
from typing import List, Optional, Dict
from app.services.book_store import BookStore
import os
import difflib

router = APIRouter(tags=["books"])

# Global book store (initialized at app startup)
_store: Optional[BookStore] = None


# ============= Pagination & Search Helpers =============

def _paginate_results(results: List[Dict], page: int = 1, limit: int = 10) -> Dict:
    """Paginate results and return with metadata.
    
    Args:
        results: Full list of results
        page: Page number (1-indexed)
        limit: Results per page
    
    Returns:
        Dict with paginated results and pagination metadata
    """
    total = len(results)
    total_pages = max(1, (total + limit - 1) // limit)  # ceiling division
    
    # Allow page to be any value; if out of range, return empty list
    page = max(1, page)  # Ensure page >= 1
    
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
    query_lower = query.lower().strip()
    
    # Check if it matches a known author (simple heuristic: contains common author names)
    author_results = store.search_by_author(query)
    if author_results:
        return 'author'
    
    # Check if it matches a known category
    category_results = store.search_by_category(query)
    if category_results:
        return 'category'
    
    # Default to title search
    return 'title'


def _smart_search(query: str, store: BookStore) -> List[Dict]:
    """Perform smart search across title, author, and category.
    
    Combines results from all search types and deduplicates by ISBN.
    """
    seen_isbns = {}
    results = []
    
    # Try author search first (most specific)
    author_results = store.search_by_author(query)
    for book in author_results:
        isbn = book.get('isbn13') or book.get('isbn10')
        if isbn and isbn not in seen_isbns:
            seen_isbns[isbn] = True
            results.append(book)
    
    # Then category search (with typo tolerance)
    _, category_results = _resolve_category_query(query, store)
    for book in category_results:
        isbn = book.get('isbn13') or book.get('isbn10')
        if isbn and isbn not in seen_isbns:
            seen_isbns[isbn] = True
            results.append(book)
    
    # Finally title search (most results)
    title_results = store.search_by_title(query)
    for book in title_results:
        isbn = book.get('isbn13') or book.get('isbn10')
        if isbn and isbn not in seen_isbns:
            seen_isbns[isbn] = True
            results.append(book)
    
    # Sort by rating (most relevant first)
    results.sort(key=lambda b: (float(b.get('average_rating', 0)), int(b.get('ratings_count', 0))), reverse=True)
    
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
        # Indicate presence so frontend can distinguish missing results without relying on HTTP status
        return {
            'found': True,
            'id': book_dict.get('isbn13') or book_dict.get('isbn10'),
            'isbn13': book_dict.get('isbn13', ''),
            'isbn10': book_dict.get('isbn10', ''),
            'title': book_dict.get('title', ''),
            'author': book_dict.get('authors', ''),  # Rename for frontend
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
            # Library-specific (can be filled from separate DB)
            'available': True,  # TODO: Check from library inventory
            'location': None,   # TODO: Get from library system
            'callNumber': None, # TODO: Get from library system
        }


# ============= API Endpoints =============

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
            # Assume book_type is stored in a 'type' or similar field, fallback to empty string
            filtered = [b for b in filtered if b.get('type', '').lower() == book_type.lower()]
        if genre is not None:
            # Check if genre/category is in the book's categories
            filtered = [b for b in filtered if genre.lower() in (b.get('categories', '') or '').lower()]
        return filtered

    if not query:
        # No search query provided: return most recent books across catalog
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

        # Apply filters before pagination
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

    # Detect typo-corrected category match so frontend can show
    # "Showing results for <resolved_category>"
    exact_category_results = store.search_by_category(query)
    resolved_category, resolved_category_results = _resolve_category_query(query, store)
    category_correction_applied = (
        not exact_category_results
        and bool(resolved_category_results)
        and resolved_category.lower() != query.lower().strip()
    )

    # Perform smart search
    all_results = _smart_search(query, store)
    # Apply filters before pagination
    filtered_results = _apply_filters(all_results)
    # Convert to response format
    book_responses = [BookResponse.from_dict(b) for b in filtered_results]
    # Paginate
    paginated = _paginate_results(book_responses, page=page, limit=limit)
    return {
        'query': query,
        'search_type': 'smart',  # Indicates multi-source search
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
            # Return 200 with explicit not-found payload instead of HTTP 404
            return {
                'found': False,
                'isbn': isbn,
                'message': f"Book not found: {isbn}",
            }
        
        resp = BookResponse.from_dict(book)
        # Ensure the response explicitly marks presence
        if isinstance(resp, dict):
            resp['found'] = True
        return resp
    except Exception as e:
        print(f"❌ Error in get_book: {e}")
        raise


@router.get("/{isbn}/similar")
def get_similar_books(isbn: str, limit: int = Query(50, ge=1, le=100)):
    """Get similar books for a given ISBN.
    
    Uses Jaccard similarity on categories + rating quality boost.
    
    Example: GET /api/books/9780439785969/similar?limit=50
    """
    store = get_store()
    book = store.get_book(isbn)

    if not book:
        # Return a structured not-found response instead of HTTP 404
        return {
            'found': False,
            'isbn': isbn,
            'message': f"Book not found: {isbn}",
            'book': None,
            'similar_books': [],
            'total_similar': 0,
        }

    # Get the target book
    target_response = BookResponse.from_dict(book)
    if isinstance(target_response, dict):
        target_response['found'] = True
    
    # Get similar books
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

    # Keep sorting behavior consistent with get_books_by_category, but do not hard-cap.
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
    all_results = store.get_top_rated_books(limit=500)  # Get more to paginate
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

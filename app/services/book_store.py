#!/usr/bin/env python3
"""Book Data Store: In-memory hash table for fast book lookups and recommendations.

Loads:
1. All books from enriched CSV
2. Precomputed recommendations from JSON index

Performance:
- Book lookup: O(1) < 1ms
- Get 50 recommendations: O(1) < 1ms
- Memory: ~250MB for 354K books

Usage:
  from app.services.book_store import BookStore
  
  # Initialize at app startup
  store = BookStore('app/data/csv/enriched_books.csv', 'app/services/book_recommendations.json')
  
  # Fast lookups
  book = store.get_book('9780439785969')  # O(1)
  similar = store.get_similar_books('9780439785969', limit=50)  # O(1)
"""

import csv
import json
import math
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class BookStore:
    """In-memory book store with fast lookups and precomputed recommendations."""
    
    def __init__(self, csv_path: str, recommendations_path: Optional[str] = None):
        """Initialize book store by loading CSV and recommendations."""
        self.books_by_isbn = {}
        self.recommendations = {}
        self.recommendations_path = recommendations_path
        self.indexes = {
            'by_author': {},
            'by_category': {},
            'by_title': {},
        }
        
        self.load_books(csv_path)
        # Don't load recommendations on init to avoid segfault
        # They will be loaded lazily when requested
        print(f"📝 Recommendations will be loaded lazily from: {recommendations_path}")
    
    
    def load_books(self, csv_path: str):
        """Load all books from CSV into memory."""
        print(f"Loading books from {csv_path}...")
        start_time = time.time()
        
        with open(csv_path, 'r', encoding='utf-8', errors='replace', newline='') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i % 100000 == 0:
                    print(f"  Loaded {i} books...")
                
                # Primary key: ISBN13 (prefer over ISBN10)
                isbn = row.get('isbn13') or row.get('isbn10') or row.get('ISBN')
                if not isbn:
                    continue
                
                # Store book data
                book = {
                    'isbn13': row.get('isbn13', ''),
                    'isbn10': row.get('isbn10', ''),
                    'title': row.get('title', ''),
                    'authors': row.get('authors', ''),
                    'publisher': row.get('publisher', ''),
                    'published_year': row.get('published_year', ''),
                    'description': row.get('description', ''),
                    'categories': row.get('categories', ''),
                    'average_rating': float(row.get('average_rating', 0) or 0),
                    'ratings_count': int(row.get('ratings_count', 0) or 0),
                    'num_pages': row.get('num_pages', ''),
                    'language_code': row.get('language_code', ''),
                    'thumbnail_m': row.get('thumbnail_m', ''),
                    'thumbnail_s': row.get('thumbnail_s', ''),
                    'thumbnail_l': row.get('thumbnail_l', ''),
                }
                
                self.books_by_isbn[isbn] = book
                
                # Index by alternate ISBN
                if row.get('isbn10') and row.get('isbn10') != isbn:
                    self.books_by_isbn[row['isbn10']] = book
                
                # Index by author (for author search)
                for author in self._parse_authors(book['authors']):
                    if author not in self.indexes['by_author']:
                        self.indexes['by_author'][author] = []
                    self.indexes['by_author'][author].append(isbn)
                
                # Index by category (for browsing)
                for category in self._parse_categories(book['categories']):
                    if category not in self.indexes['by_category']:
                        self.indexes['by_category'][category] = []
                    self.indexes['by_category'][category].append(isbn)
                
                # Index by title words (for title search)
                for word in self._extract_title_words(book['title']):
                    if word not in self.indexes['by_title']:
                        self.indexes['by_title'][word] = []
                    self.indexes['by_title'][word].append(isbn)
        
        elapsed = time.time() - start_time
        print(f"✓ Loaded {len(self.books_by_isbn)} book records in {elapsed:.2f}s")
    
    def load_recommendations(self, json_path: str):
        """Load precomputed recommendations from JSON."""
        print(f"Loading recommendations from {json_path}...")
        start_time = time.time()
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Convert back to list of tuples
            for isbn, similar_list in data.items():
                self.recommendations[isbn] = [
                    (item['isbn'], item['score']) for item in similar_list
                ]
        
        elapsed = time.time() - start_time
        coverage = 100 * len(self.recommendations) / len(self.books_by_isbn) if self.books_by_isbn else 0
        print(f"✓ Loaded recommendations for {len(self.recommendations)} books ({coverage:.1f}% coverage) in {elapsed:.2f}s")
    
    @staticmethod
    def _parse_authors(authors_str: str) -> List[str]:
        """Parse comma/semicolon-separated authors."""
        if not authors_str:
            return []
        # Split by comma or semicolon
        authors = [a.strip() for a in authors_str.replace(';', ',').split(',')]
        return [a.lower() for a in authors if a]
    
    @staticmethod
    def _parse_categories(cat_str: str) -> List[str]:
        """Parse comma-separated categories."""
        if not cat_str:
            return []
        return [c.strip().lower() for c in cat_str.split(',') if c.strip()]
    
    @staticmethod
    def _extract_title_words(title: str, min_length: int = 3) -> List[str]:
        """Extract searchable words from title."""
        if not title:
            return []
        # Simple tokenization, lowercase, filter by length
        words = title.lower().split()
        return [w.strip('.,!?"\'') for w in words if len(w) >= min_length]

    @staticmethod
    def _safe_year(value) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _tokenize_text(text: str) -> set:
        if not text:
            return set()
        return set(re.findall(r"[a-z0-9]+", text.lower()))

    def _rerank_similar_candidates(self, target_book: Dict, similar_data: List[Tuple[str, float]]) -> List[Tuple[str, float]]:
        target_categories = set(self._parse_categories(target_book.get('categories', '')))
        target_authors = set(self._parse_authors(target_book.get('authors', '')))
        target_year = self._safe_year(target_book.get('published_year'))
        target_title_tokens = set(self._extract_title_words(target_book.get('title', '')))
        target_desc_tokens = self._tokenize_text(target_book.get('description', ''))

        reranked = []
        for sim_isbn, base_score in similar_data:
            sim_book = self.books_by_isbn.get(sim_isbn)
            if not sim_book:
                continue

            sim_categories = set(self._parse_categories(sim_book.get('categories', '')))
            sim_authors = set(self._parse_authors(sim_book.get('authors', '')))
            sim_year = self._safe_year(sim_book.get('published_year'))
            sim_title_tokens = set(self._extract_title_words(sim_book.get('title', '')))
            sim_desc_tokens = self._tokenize_text(sim_book.get('description', ''))

            # Category overlap: strong genre alignment signal.
            union_cats = target_categories | sim_categories
            category_overlap = (len(target_categories & sim_categories) / len(union_cats)) if union_cats else 0.0

            # Author affinity: direct author match gets a strong boost.
            author_match = 1.0 if target_authors and sim_authors and (target_authors & sim_authors) else 0.0

            # Year proximity: closer publication years are usually more relevant.
            if target_year is not None and sim_year is not None:
                year_diff = abs(target_year - sim_year)
                year_proximity = max(0.0, 1.0 - (year_diff / 20.0))
            else:
                year_proximity = 0.0

            # Title and description overlap for semantic surface alignment.
            title_overlap = (len(target_title_tokens & sim_title_tokens) / len(target_title_tokens | sim_title_tokens)) if (target_title_tokens or sim_title_tokens) else 0.0
            desc_overlap = (len(target_desc_tokens & sim_desc_tokens) / len(target_desc_tokens | sim_desc_tokens)) if (target_desc_tokens or sim_desc_tokens) else 0.0

            rating = float(sim_book.get('average_rating', 0) or 0)
            ratings_count = int(sim_book.get('ratings_count', 0) or 0)
            quality_score = min(1.0, (rating / 5.0) * (math.log1p(ratings_count) / 12.0))

            # Weighted blend: keep base score dominant, then refine with metadata.
            rerank_score = (
                0.45 * float(base_score) +
                0.20 * category_overlap +
                0.12 * author_match +
                0.08 * year_proximity +
                0.07 * title_overlap +
                0.05 * desc_overlap +
                0.03 * quality_score
            )
            reranked.append((sim_isbn, rerank_score))

        reranked.sort(key=lambda x: x[1], reverse=True)
        return reranked
    
    # ============= API Methods =============
    
    def get_book(self, isbn: str) -> Optional[Dict]:
        """Get a single book by ISBN (O(1))."""
        return self.books_by_isbn.get(isbn)
    
    def get_similar_books(self, isbn: str, limit: int = 100) -> List[Dict]:
        """Get similar books with reranked scores (lazy-loads recommendations)."""
        # Load recommendations on first access
        if not self.recommendations and self.recommendations_path:
            self._lazy_load_recommendations()
        
        if isbn not in self.recommendations:
            return []

        target_book = self.get_book(isbn)
        if not target_book:
            return []
        
        # Take top 100 precomputed candidates, then rerank online.
        candidate_data = self.recommendations[isbn][:100]
        reranked_data = self._rerank_similar_candidates(target_book, candidate_data)
        final_data = reranked_data[: min(limit, 100)]
        
        return [
            {
                'book': self.books_by_isbn.get(sim_isbn),
                'similarity_score': score,
            }
            for sim_isbn, score in final_data
            if sim_isbn in self.books_by_isbn
        ]
    
    def _lazy_load_recommendations(self):
        """Load recommendations from JSON on first request (lazy loading)."""
        if not self.recommendations_path or not Path(self.recommendations_path).exists():
            return
        
        print(f"Loading recommendations from {self.recommendations_path}...")
        try:
            with open(self.recommendations_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Convert back to list of tuples
                for isbn, similar_list in data.items():
                    self.recommendations[isbn] = [
                        (item['isbn'], item['score']) for item in similar_list
                    ]
            
            coverage = 100 * len(self.recommendations) / len(self.books_by_isbn) if self.books_by_isbn else 0
            print(f"✓ Loaded recommendations for {len(self.recommendations)} books ({coverage:.1f}% coverage)")
        except Exception as e:
            print(f"⚠️ Could not load recommendations: {e}")
    
    def search_by_author(self, author_name: str) -> List[Dict]:
        """Search books by author (O(k) where k = books by author)."""
        author_lower = author_name.lower()
        isbns = self.indexes['by_author'].get(author_lower, [])
        return [self.books_by_isbn[isbn] for isbn in isbns if isbn in self.books_by_isbn]
    
    def search_by_category(self, category: str) -> List[Dict]:
        """Search books by category (O(k) where k = books in category)."""
        category_lower = category.lower()
        isbns = self.indexes['by_category'].get(category_lower, [])
        return [self.books_by_isbn[isbn] for isbn in isbns if isbn in self.books_by_isbn]
    
    def search_by_title(self, query: str) -> List[Dict]:
        """Simple title search (O(k) where k = books with matching words)."""
        query_words = self._extract_title_words(query)
        if not query_words:
            return []
        
        # Find books that have most query words in title
        candidates = {}
        for word in query_words:
            isbns = self.indexes['by_title'].get(word, [])
            for isbn in isbns:
                candidates[isbn] = candidates.get(isbn, 0) + 1
        
        # Sort by number of matching words
        sorted_isbns = sorted(candidates.items(), key=lambda x: x[1], reverse=True)
        return [self.books_by_isbn[isbn] for isbn, _ in sorted_isbns if isbn in self.books_by_isbn]
    
    def get_top_rated_books(self, limit: int = 100) -> List[Dict]:
        """Get top-rated books (O(n log n) but cached in practice)."""
        books = list(self.books_by_isbn.values())
        # Default dict to avoid duplicates
        unique_books = {}
        for book in books:
            isbn = book['isbn13'] or book['isbn10']
            if isbn not in unique_books:
                unique_books[isbn] = book
        
        sorted_books = sorted(
            unique_books.values(),
            key=lambda b: (b['average_rating'], b['ratings_count']),
            reverse=True
        )
        return sorted_books[:limit]
    
    def get_books_by_category(self, category: str, limit: int = 100) -> List[Dict]:
        """Get books in a category."""
        books = self.search_by_category(category)
        # Sort by rating
        books.sort(key=lambda b: (b['average_rating'], b['ratings_count']), reverse=True)
        return books[:limit]
    
    # ============= Stats =============
    
    def get_stats(self) -> Dict:
        """Get store statistics."""
        unique_books = len(set(
            b.get('isbn13') or b.get('isbn10') 
            for b in self.books_by_isbn.values()
        ))
        
        books_with_recommendations = len(self.recommendations)
        books_with_categories = sum(
            1 for b in self.books_by_isbn.values()
            if b.get('categories') and b['categories'].strip()
        )
        
        return {
            'total_isbn_entries': len(self.books_by_isbn),
            'unique_books': unique_books,
            'books_with_recommendations': books_with_recommendations,
            'books_with_categories': books_with_categories,
            'authors_indexed': len(self.indexes['by_author']),
            'categories_indexed': len(self.indexes['by_category']),
        }


# ============= Example Usage =============

if __name__ == '__main__':
    # Initialize store
    store = BookStore(
        'app/data/csv/enriched_books.csv',
        'app/services/book_recommendations.json'
    )
    
    # Print stats
    stats = store.get_stats()
    print("\n📊 BookStore Stats:")
    for key, value in stats.items():
        print(f"  {key}: {value:,}")
    
    # Test lookup
    print("\n🔍 Example: Harry Potter")
    book = store.get_book('9780439785969')
    if book:
        print(f"  Title: {book['title']}")
        print(f"  Author: {book['authors']}")
        print(f"  Rating: {book['average_rating']:.2f} ({book['ratings_count']:,} votes)")
        
        print(f"\n  Similar books (top 5):")
        similar = store.get_similar_books('9780439785969', limit=5)
        for i, item in enumerate(similar, 1):
            sim_book = item['book']
            score = item['similarity_score']
            print(f"    {i}. {sim_book['title']} (score: {score:.3f})")

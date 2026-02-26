#!/usr/bin/env python3
"""Recommendation engine using Jaccard similarity on enriched categories.

Precomputes top 50 similar books for each book at startup.
Uses in-memory hash table for O(1) lookup speeds.

Usage:
  python scripts/build_recommendation_index.py --input app/data/csv/enriched_books.csv --output app/data/services/book_recommendations.json
"""

import csv
import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict


def parse_categories(cat_str: str) -> set:
    """Parse comma-separated categories into a set."""
    if not cat_str or not cat_str.strip():
        return set()
    return set(c.strip().lower() for c in cat_str.split(',') if c.strip())


def jaccard_similarity(set1: set, set2: set) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set1 and not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


def compute_similar_books(
    books: Dict[str, Dict],
    target_isbn: str,
    limit: int = 50,
) -> List[Tuple[str, float]]:
    """Find top N similar books using Jaccard similarity on categories.
    
    Returns: [(isbn, similarity_score), ...]
    """
    target_book = books[target_isbn]
    target_categories = parse_categories(target_book['categories'])
    
    if not target_categories:
        # If no categories, fall back to same author or rating proximity
        return fallback_recommendations(books, target_isbn, limit)
    
    scores = []
    for other_isbn, other_book in books.items():
        if other_isbn == target_isbn:
            continue
        
        other_categories = parse_categories(other_book['categories'])
        
        # Jaccard similarity on categories
        jaccard = jaccard_similarity(target_categories, other_categories)
        
        # Boost by rating quality (books with more ratings are more reliable)
        rating_boost = 0
        try:
            ratings_count = int(other_book.get('ratings_count', 0) or 0)
            rating_boost = min(ratings_count / 10000, 0.5)  # Max +0.5 boost
        except (ValueError, TypeError):
            pass
        
        total_score = jaccard + rating_boost
        
        if jaccard > 0 or rating_boost > 0:  # Only include if some similarity
            scores.append((other_isbn, total_score))
    
    # Sort by score descending
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:limit]


def fallback_recommendations(
    books: Dict[str, Dict],
    target_isbn: str,
    limit: int = 50,
) -> List[Tuple[str, float]]:
    """Fallback recommendations for books with no categories.
    
    Uses: similar authors, similar title keywords, rating proximity
    """
    target_book = books[target_isbn]
    target_authors = set(a.strip().lower() for a in target_book.get('authors', '').split(',') if a.strip())
    target_title_words = set(target_book.get('title', '').lower().split())
    
    try:
        target_rating = float(target_book.get('average_rating', 0) or 0)
    except (ValueError, TypeError):
        target_rating = 0
    
    scores = []
    for other_isbn, other_book in books.items():
        if other_isbn == target_isbn:
            continue
        
        score = 0
        
        # Author match (50%)
        other_authors = set(a.strip().lower() for a in other_book.get('authors', '').split(',') if a.strip())
        author_overlap = len(target_authors & other_authors)
        if author_overlap > 0:
            score += author_overlap * 0.5
        
        # Title keyword match (20%)
        other_title_words = set(other_book.get('title', '').lower().split())
        title_overlap = len(target_title_words & other_title_words)
        if title_overlap > 0:
            score += title_overlap * 0.1
        
        # Rating proximity (30%)
        try:
            other_rating = float(other_book.get('average_rating', 0) or 0)
            rating_diff = abs(target_rating - other_rating)
            rating_score = max(0, 1.5 - rating_diff)  # Max 1.5 points
            score += rating_score * 0.2
        except (ValueError, TypeError):
            pass
        
        if score > 0:
            scores.append((other_isbn, score))
    
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:limit]


def load_books(csv_path: str) -> Dict[str, Dict]:
    """Load books from CSV into memory."""
    books = {}
    print(f"Loading books from {csv_path}...")
    
    with open(csv_path, 'r', encoding='utf-8', errors='replace', newline='') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i % 50000 == 0:
                print(f"  Loaded {i} books...")
            
            isbn = row.get('isbn13') or row.get('isbn10') or row.get('ISBN')
            if not isbn:
                continue
            
            books[isbn] = {
                'isbn13': row.get('isbn13', ''),
                'isbn10': row.get('isbn10', ''),
                'title': row.get('title', ''),
                'authors': row.get('authors', ''),
                'categories': row.get('categories', ''),
                'publisher': row.get('publisher', ''),
                'published_year': row.get('published_year', ''),
                'average_rating': row.get('average_rating', ''),
                'ratings_count': row.get('ratings_count', ''),
                'description': row.get('description', ''),
                'thumbnail_m': row.get('thumbnail_m', ''),
            }
    
    print(f"✓ Loaded {len(books)} books\n")
    return books


def build_recommendations(books: Dict[str, Dict]) -> Dict[str, List[Tuple[str, float]]]:
    """Build recommendation index for all books."""
    print("Computing recommendations for all books...")
    print("(This may take 10-30 minutes)\n")
    
    recommendations = {}
    isbn_list = list(books.keys())
    
    for i, isbn in enumerate(isbn_list):
        if i % 10000 == 0:
            percentage = 100 * i / len(isbn_list)
            print(f"  [{percentage:.1f}%] Processed {i}/{len(isbn_list)} books...")
        
        similar = compute_similar_books(books, isbn, limit=50)
        recommendations[isbn] = similar
    
    print(f"✓ Computed recommendations for {len(recommendations)} books\n")
    return recommendations


def save_recommendations(
    recommendations: Dict[str, List[Tuple[str, float]]],
    output_path: str,
):
    """Save recommendations as JSON."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert to JSON-serializable format
    json_data = {}
    for isbn, similar_list in recommendations.items():
        json_data[isbn] = [
            {"isbn": sim_isbn, "score": score}
            for sim_isbn, score in similar_list
        ]
    
    print(f"Saving recommendations to {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=0)  # No indent for file size
    
    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"✓ Saved {len(json_data)} recommendation sets ({file_size_mb:.1f}MB)")


def main():
    parser = argparse.ArgumentParser(description="Build book recommendation index")
    parser.add_argument('--input', required=True, help='Input CSV path')
    parser.add_argument('--output', default='app/services/book_recommendations.json')
    
    args = parser.parse_args()
    
    # Load books
    books = load_books(args.input)
    
    # Build recommendations
    recommendations = build_recommendations(books)
    
    # Save
    save_recommendations(recommendations, args.output)
    
    print("\n✅ Recommendation index ready!")
    print(f"   Location: {args.output}")
    print(f"   Usage: Load into memory on app startup")


if __name__ == '__main__':
    main()

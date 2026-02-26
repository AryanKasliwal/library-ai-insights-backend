#!/usr/bin/env python3
"""Merge three CSV files (books.csv, books 2.csv, combined_books_data.csv) into one.

Strategy:
1. Use isbn13 as primary key, fallback to isbn10/isbn for merging
2. combined_books_data.csv (most rows) is used as root; fill in missing data from others
3. Reconcile column names (title/Book-Title, authors/Book-Author, etc.)
4. For conflicting values, prefer data from largest dataset
5. Weighted average ratings: (avg_rating * count) / total_count across all sources

Output: app/data/csv/final_merged_books.csv
"""

import csv
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Any


def normalize_isbn(isbn_str: str) -> str:
    """Strip quotes and whitespace from ISBN."""
    return (isbn_str or "").strip().strip('"') if isbn_str else ""


def normalize_rating(rating_val: Any) -> float:
    """Normalize rating to 0-5 scale. If > 5, assume it's out of 10 and divide by 2."""
    try:
        val = float(rating_val) if rating_val else 0.0
        if val > 5.0:
            val = val / 2.0
        return round(val, 4)
    except (ValueError, TypeError):
        return 0.0


def load_books_csv(path: Path) -> Dict[str, Dict[str, Any]]:
    """Load books.csv (isbn13 as key)."""
    books = {}
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row or not row.get("isbn13"):
                continue
            isbn13 = normalize_isbn(row["isbn13"])
            if not isbn13:
                continue
            books[("isbn13", isbn13)] = {
                "isbn13": isbn13,
                "isbn10": normalize_isbn(row.get("isbn10", "")),
                "title": row.get("title", ""),
                "subtitle": row.get("subtitle", ""),
                "authors": row.get("authors", ""),
                "categories": row.get("categories", ""),
                "thumbnail": row.get("thumbnail", ""),
                "description": row.get("description", ""),
                "published_year": row.get("published_year", ""),
                "average_rating": str(normalize_rating(row.get("average_rating", ""))),
                "num_pages": row.get("num_pages", ""),
                "ratings_count": row.get("ratings_count", ""),
                "_source": "books.csv",
            }
    return books


def load_books2_csv(path: Path) -> Dict[str, Dict[str, Any]]:
    """Load books 2.csv (isbn13 as key, fallback isbn)."""
    books = {}
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row:
                continue
            isbn13 = normalize_isbn(row.get("isbn13", ""))
            isbn = normalize_isbn(row.get("isbn", ""))
            key = None
            if isbn13:
                key = ("isbn13", isbn13)
            elif isbn:
                key = ("isbn", isbn)
            if not key:
                continue
            books[key] = {
                "bookID": row.get("bookID", ""),
                "title": row.get("title", ""),
                "authors": row.get("authors", ""),
                "average_rating": str(normalize_rating(row.get("average_rating", ""))),
                "isbn": isbn,
                "isbn13": isbn13,
                "language_code": row.get("language_code", ""),
                "num_pages": row.get("num_pages", ""),
                "ratings_count": row.get("ratings_count", ""),
                "text_reviews_count": row.get("text_reviews_count", ""),
                "publication_date": row.get("publication_date", ""),
                "publisher": row.get("publisher", ""),
                "_source": "books 2.csv",
            }
    return books


def load_combined_csv(path: Path) -> Dict[str, Dict[str, Any]]:
    """Load combined_books_data.csv (ISBN as key, prefer isbn13)."""
    books = {}
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row or not row.get("ISBN"):
                continue
            isbn = normalize_isbn(row["ISBN"])
            if not isbn:
                continue
            # Try to detect if it's isbn13 or isbn10
            # ISBN13 is 13 digits, ISBN10 is 10 characters
            is_isbn13 = len(isbn) == 13 and isbn.isdigit()
            key_type = "isbn13" if is_isbn13 else "isbn10"
            key = (key_type, isbn)
            books[key] = {
                "ISBN": isbn,
                "Book-Title": row.get("Book-Title", ""),
                "Book-Author": row.get("Book-Author", ""),
                "Year-Of-Publication": row.get("Year-Of-Publication", ""),
                "Publisher": row.get("Publisher", ""),
                "Image-URL-S": row.get("Image-URL-S", ""),
                "Image-URL-M": row.get("Image-URL-M", ""),
                "Image-URL-L": row.get("Image-URL-L", ""),
                "ratings_count_raw": row.get("ratings_count_raw", ""),
                "average_rating_raw": str(normalize_rating(row.get("average_rating_raw", ""))),
                "_source": "combined_books_data.csv",
            }
    return books


def merge_by_isbn(
    books_csv: Dict,
    books2_csv: Dict,
    combined: Dict,
) -> Dict[str, Dict[str, Any]]:
    """Merge all books by ISBN13 (primary) or ISBN10 (fallback).
    
    Strategy:
    - Use combined_books_data.csv as root (largest dataset)
    - Fill missing fields from books 2.csv and books.csv
    - For conflicts, prefer combined > books2 > books
    """
    merged = {}
    
    # Collect all ISBNs from all sources
    all_keys = set(combined.keys()) | set(books_csv.keys()) | set(books2_csv.keys())
    
    for key in sorted(all_keys):
        combined_row = combined.get(key)
        books_row = books_csv.get(key)
        books2_row = books2_csv.get(key)
        
        # Build merged record
        record = {
            "isbn13": "",
            "isbn10": "",
            "title": "",
            "authors": "",
            "publisher": "",
            "description": "",
            "categories": "",
            "thumbnail_s": "",
            "thumbnail_m": "",
            "thumbnail_l": "",
            "published_year": "",
            "num_pages": "",
            "average_rating": "",
            "ratings_count": "",
            "language_code": "",
            "text_reviews_count": "",
            "publication_date": "",
            "bookID": "",
            "_sources": [],
        }
        
        # Extract ISBN from key
        key_type, isbn_val = key
        if key_type == "isbn13":
            record["isbn13"] = isbn_val
        else:
            record["isbn10"] = isbn_val
        
        # Layer 1: Use combined as primary
        if combined_row:
            record["_sources"].append("combined_books_data.csv")
            record["title"] = record["title"] or combined_row.get("Book-Title", "")
            record["authors"] = record["authors"] or combined_row.get("Book-Author", "")
            record["publisher"] = record["publisher"] or combined_row.get("Publisher", "")
            record["published_year"] = record["published_year"] or combined_row.get("Year-Of-Publication", "")
            record["thumbnail_s"] = combined_row.get("Image-URL-S", "")
            record["thumbnail_m"] = combined_row.get("Image-URL-M", "")
            record["thumbnail_l"] = combined_row.get("Image-URL-L", "")
            record["isbn13"] = record["isbn13"] or combined_row.get("ISBN", "")
            avg_rating_raw = combined_row.get("average_rating_raw", "")
            count_raw = combined_row.get("ratings_count_raw", "")
            if avg_rating_raw and count_raw:
                record["average_rating"] = avg_rating_raw
                record["ratings_count"] = count_raw
        
        # Layer 2: Fill gaps from books2
        if books2_row:
            if not record["_sources"] or "books 2.csv" not in record["_sources"]:
                record["_sources"].append("books 2.csv")
            record["title"] = record["title"] or books2_row.get("title", "")
            record["authors"] = record["authors"] or books2_row.get("authors", "")
            record["publisher"] = record["publisher"] or books2_row.get("publisher", "")
            record["publication_date"] = record["publication_date"] or books2_row.get("publication_date", "")
            record["language_code"] = books2_row.get("language_code", "")
            record["num_pages"] = record["num_pages"] or books2_row.get("num_pages", "")
            record["text_reviews_count"] = books2_row.get("text_reviews_count", "")
            record["bookID"] = books2_row.get("bookID", "")
            record["isbn13"] = record["isbn13"] or books2_row.get("isbn13", "")
            record["isbn10"] = record["isbn10"] or books2_row.get("isbn", "")
            if books2_row.get("average_rating") and books2_row.get("ratings_count"):
                # Store for weighted average calculation
                # Only use if we don't already have combined data
                if not combined_row:
                    record["average_rating"] = books2_row.get("average_rating", "")
                    record["ratings_count"] = books2_row.get("ratings_count", "")
        
        # Layer 3: Fill remaining gaps from books.csv
        if books_row:
            if not record["_sources"] or "books.csv" not in record["_sources"]:
                record["_sources"].append("books.csv")
            record["title"] = record["title"] or books_row.get("title", "")
            record["authors"] = record["authors"] or books_row.get("authors", "")
            record["description"] = record["description"] or books_row.get("description", "")
            record["categories"] = books_row.get("categories", "")
            record["published_year"] = record["published_year"] or books_row.get("published_year", "")
            record["num_pages"] = record["num_pages"] or books_row.get("num_pages", "")
            record["isbn10"] = record["isbn10"] or books_row.get("isbn10", "")
            record["isbn13"] = record["isbn13"] or books_row.get("isbn13", "")
            # For thumbnail: if combined has URLs, use those; otherwise use books.csv thumbnail
            if not record["thumbnail_s"]:
                thumb = books_row.get("thumbnail", "")
                record["thumbnail_s"] = thumb
                record["thumbnail_m"] = thumb
                record["thumbnail_l"] = thumb
            if books_row.get("average_rating") and books_row.get("ratings_count"):
                if not combined_row and not books2_row:
                    record["average_rating"] = books_row.get("average_rating", "")
                    record["ratings_count"] = books_row.get("ratings_count", "")
        
        merged[key] = record
    
    return merged


def calculate_weighted_averages(merged_dict: Dict) -> Dict:
    """Calculate weighted average ratings across all sources for each book.
    
    For books with ratings data from multiple sources, compute:
    weighted_avg = sum(avg_rating * count) / sum(count)
    """
    # Group by ISBN (deduplicate similar ISBNs)
    isbn_groups = defaultdict(list)
    for key, record in merged_dict.items():
        # Use isbn13 as primary, isbn10 as fallback
        isbn = record["isbn13"] or record["isbn10"]
        if isbn:
            isbn_groups[isbn].append(record)
    
    # Compute weighted averages
    for isbn, records in isbn_groups.items():
        if len(records) == 1:
            # Single record, no aggregation needed
            continue
        
        # Multiple sources for same ISBN
        total_count = 0
        total_weighted_sum = 0
        
        for record in records:
            try:
                avg = float(record["average_rating"]) if record["average_rating"] else 0
                count = int(record["ratings_count"]) if record["ratings_count"] else 0
                if avg > 0 and count > 0:
                    total_weighted_sum += avg * count
                    total_count += count
            except (ValueError, TypeError):
                pass
        
        if total_count > 0:
            weighted_avg = total_weighted_sum / total_count
            # Update all records for this ISBN with the computed weighted average
            for record in records:
                record["average_rating"] = round(weighted_avg, 4)
                record["ratings_count"] = total_count
    
    return merged_dict


def write_merged_csv(output_path: Path, merged: Dict):
    """Write merged data to CSV."""
    fieldnames = [
        "isbn13",
        "isbn10",
        "title",
        "authors",
        "publisher",
        "description",
        "categories",
        "thumbnail_s",
        "thumbnail_m",
        "thumbnail_l",
        "published_year",
        "num_pages",
        "average_rating",
        "ratings_count",
        "language_code",
        "text_reviews_count",
        "publication_date",
        "bookID",
        "_sources",
    ]
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in merged.values():
            writer.writerow(record)


def main():
    import argparse
    
    p = argparse.ArgumentParser(
        description="Merge books.csv, books 2.csv, and combined_books_data.csv"
    )
    p.add_argument(
        "--books",
        default="app/data/csv/books.csv",
        help="Path to books.csv"
    )
    p.add_argument(
        "--books2",
        default="app/data/csv/books 2.csv",
        help="Path to books 2.csv"
    )
    p.add_argument(
        "--combined",
        default="app/data/csv/combined_books_data.csv",
        help="Path to combined_books_data.csv"
    )
    p.add_argument(
        "--output",
        default="app/data/csv/final_merged_books.csv",
        help="Output CSV path"
    )
    
    args = p.parse_args()
    
    print("Loading books.csv...")
    books_csv = load_books_csv(Path(args.books))
    print(f"  Loaded {len(books_csv)} entries from books.csv")
    
    print("Loading books 2.csv...")
    books2_csv = load_books2_csv(Path(args.books2))
    print(f"  Loaded {len(books2_csv)} entries from books 2.csv")
    
    print("Loading combined_books_data.csv...")
    combined = load_combined_csv(Path(args.combined))
    print(f"  Loaded {len(combined)} entries from combined_books_data.csv")
    
    print("Merging by ISBN...")
    merged = merge_by_isbn(books_csv, books2_csv, combined)
    print(f"  Merged into {len(merged)} unique ISBN entries")
    
    print("Calculating weighted average ratings...")
    merged = calculate_weighted_averages(merged)
    
    print(f"Writing to {args.output}...")
    write_merged_csv(Path(args.output), merged)
    print(f"✓ Done! Output: {args.output}")


if __name__ == "__main__":
    main()

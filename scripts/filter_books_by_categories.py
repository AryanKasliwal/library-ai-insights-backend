#!/usr/bin/env python3
"""Filter enriched_books.csv to keep only books with categories.

This creates a smaller, cleaner dataset perfect for prototyping.
- Input: 353,990 books (many without categories)
- Output: ~111,827 books (all with categories)
- Benefit: 10x faster recommendation indexing (45-60 min vs 8-12 hours)

Usage:
  python scripts/filter_books_by_categories.py \
    --input app/data/csv/enriched_books.csv \
    --output app/data/csv/enriched_books_filtered.csv
"""

import csv
import argparse
from pathlib import Path


def filter_books(input_path: str, output_path: str) -> tuple[int, int]:
    """Filter books to keep only those with categories."""
    
    print(f"Filtering books from {input_path}...")
    
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    total_books = 0
    filtered_books = 0
    
    with open(input_path, 'r', encoding='utf-8', errors='replace', newline='') as f_in:
        reader = csv.DictReader(f_in)
        fieldnames = reader.fieldnames
        
        with open(output_path, 'w', encoding='utf-8', newline='') as f_out:
            writer = csv.DictWriter(f_out, fieldnames=fieldnames)
            writer.writeheader()
            
            for i, row in enumerate(reader):
                if i % 50000 == 0:
                    print(f"  Processing {i:,} books...")
                
                total_books += 1
                
                # Keep only if categories field is non-empty
                categories = row.get('categories', '').strip()
                if categories and len(categories) > 0 and categories != 'categories':
                    writer.writerow(row)
                    filtered_books += 1
    
    return total_books, filtered_books


def main():
    parser = argparse.ArgumentParser(description="Filter books by category presence")
    parser.add_argument('--input', required=True, help='Input CSV path')
    parser.add_argument('--output', required=True, help='Output CSV path')
    
    args = parser.parse_args()
    
    total, filtered = filter_books(args.input, args.output)
    
    print(f"\n✅ Filtering complete!")
    print(f"   Original books: {total:,}")
    print(f"   Filtered books: {filtered:,}")
    print(f"   Coverage: {100*filtered/total:.1f}%")
    print(f"   Removed: {total - filtered:,} books without categories")
    print(f"\n📊 Efficiency gain:")
    print(f"   Original pairs: {total:,}² = {total*total:,}")
    print(f"   Filtered pairs: {filtered:,}² = {filtered*filtered:,}")
    print(f"   Reduction: {100*(1 - (filtered*filtered)/(total*total)):.1f}%")
    print(f"\n💨 Time savings:")
    print(f"   Original estimate: 8-12 hours")
    print(f"   New estimate: ~45-60 minutes")
    print(f"\n📁 Output: {args.output}")


if __name__ == '__main__':
    main()

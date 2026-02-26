#!/usr/bin/env python3
"""Combine and normalize CSV files in app/data/csv/books_data.

Creates a single CSV with expanded columns from books3.csv and
aggregated rating stats from ratings.csv (ratings_count_raw, average_rating_raw).

Usage:
  python scripts/combine_books_data.py \
    --input-dir app/data/csv/books_data \
    --output app/data/csv/combined_books_data.csv
"""
from pathlib import Path
import csv
import argparse
from collections import defaultdict


def normalize_rating(rating_val) -> float:
    """Normalize rating to 0-5 scale. If > 5, assume it's out of 10 and divide by 2."""
    try:
        val = float(rating_val) if rating_val else 0.0
        if val > 5.0:
            val = val / 2.0
        return round(val, 4)
    except (ValueError, TypeError):
        return 0.0


def parse_books3(path):
    """Parse books3.csv (semicolon-delimited with quotes) into dict by ISBN."""
    books = {}
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f, delimiter=";", quotechar='"')
        for i, row in enumerate(reader):
            if not row:
                continue
            # detect header row
            first = row[0].strip().upper()
            if i == 0 and ("ISBN" in first or "BOOK-TITLE" in [c.upper() for c in row]):
                continue
            # Normalize row length to 8 expected fields
            # Expected order: ISBN;Book-Title;Book-Author;Year-Of-Publication;Publisher;Image-URL-S;Image-URL-M;Image-URL-L
            while len(row) < 8:
                row.append("")
            isbn = row[0].strip()
            books[isbn] = {
                "ISBN": isbn,
                "Book-Title": row[1].strip(),
                "Book-Author": row[2].strip(),
                "Year-Of-Publication": row[3].strip(),
                "Publisher": row[4].strip(),
                "Image-URL-S": row[5].strip(),
                "Image-URL-M": row[6].strip(),
                "Image-URL-L": row[7].strip(),
            }
    return books


def parse_ratings(path):
    """Parse ratings file with semicolon delimiter: User-ID;"ISBN";"Book-Rating".

    Returns a dict mapping ISBN -> dict(count, sum, average)
    """
    agg = defaultdict(lambda: {"count": 0, "sum": 0.0})
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f, delimiter=";", quotechar='"')
        for i, row in enumerate(reader):
            if not row:
                continue
            # Some files may include a header like User-ID
            if i == 0 and any("user" in (c or "").lower() for c in row):
                # try to detect header and skip
                if len(row) >= 3 and ("user" in (row[0] or "").lower()):
                    continue
            # We expect at least 3 columns: user_id, isbn, rating
            if len(row) < 3:
                # sometimes file may have entire line in a single column; try splitting manually
                line = row[0]
                parts = line.split(";")
            else:
                parts = row
            # normalize
            if len(parts) < 3:
                continue
            isbn = parts[1].strip().strip('"')
            try:
                rating = normalize_rating(parts[2])
            except Exception:
                # skip non-numeric ratings
                continue
            agg[isbn]["count"] += 1
            agg[isbn]["sum"] += rating

    # compute averages
    result = {}
    for isbn, v in agg.items():
        cnt = v["count"]
        summ = v["sum"]
        avg = summ / cnt if cnt else 0.0
        result[isbn] = {"ratings_count_raw": cnt, "average_rating_raw": round(avg, 4)}
    return result


def write_combined(output_path, books_map, ratings_map):
    # union of isbns
    isbns = set(books_map.keys()) | set(ratings_map.keys())
    fieldnames = [
        "ISBN",
        "Book-Title",
        "Book-Author",
        "Year-Of-Publication",
        "Publisher",
        "Image-URL-S",
        "Image-URL-M",
        "Image-URL-L",
        "ratings_count_raw",
        "average_rating_raw",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()
        for isbn in sorted(isbns):
            row = {k: "" for k in fieldnames}
            if isbn in books_map:
                row.update(books_map[isbn])
            else:
                row["ISBN"] = isbn
            if isbn in ratings_map:
                row.update(ratings_map[isbn])
            writer.writerow(row)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", default="app/data/csv/books_data")
    p.add_argument("--output", default="app/data/csv/combined_books_data.csv")
    args = p.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        raise SystemExit(f"Input directory not found: {input_dir}")

    books_map = {}
    ratings_map = {}

    # look for files
    for fp in sorted(input_dir.iterdir()):
        name = fp.name.lower()
        if not fp.is_file():
            continue
        if "books3" in name or "books-" in name or "book" in name and name.endswith(".csv"):
            try:
                parsed = parse_books3(fp)
                books_map.update(parsed)
                print(f"Parsed books file: {fp} (rows={len(parsed)})")
            except Exception as e:
                print(f"Skipping books file {fp}: {e}")
        elif "rating" in name or "ratings" in name:
            try:
                parsed = parse_ratings(fp)
                ratings_map.update(parsed)
                print(f"Parsed ratings file: {fp} (distinct_isbns={len(parsed)})")
            except Exception as e:
                print(f"Skipping ratings file {fp}: {e}")
        else:
            # try to infer format: if semicolon-delimited with ISBN in first column, treat as books3-like
            try:
                parsed = parse_books3(fp)
                if parsed:
                    books_map.update(parsed)
                    print(f"Parsed additional books-like file: {fp} (rows={len(parsed)})")
            except Exception:
                print(f"Ignored file: {fp}")

    out_path = Path(args.output)
    write_combined(out_path, books_map, ratings_map)
    print(f"Wrote combined file to: {out_path}")


if __name__ == "__main__":
    main()

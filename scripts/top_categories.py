#!/usr/bin/env python3

import argparse
import csv
from collections import Counter


def normalize_category(value: str) -> str:
    if value is None:
        return ""
    return value.strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print top N most frequent categories from a CSV column."
    )
    parser.add_argument(
        "--input",
        default="app/data/csv/final_merged_books.csv",
        help="Path to input CSV file (default: app/data/csv/final_merged_books.csv)",
    )
    parser.add_argument(
        "--column",
        default="category",
        help="Category column name (default: category)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="How many top categories to print (default: 10)",
    )

    args = parser.parse_args()

    counter = Counter()

    with open(args.input, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            raise ValueError("CSV appears empty or has no header row")

        selected_column = args.column
        if selected_column not in reader.fieldnames:
            if selected_column == "category" and "categories" in reader.fieldnames:
                selected_column = "categories"
            else:
                available = ", ".join(reader.fieldnames)
                raise ValueError(
                    f"Column '{args.column}' not found. Available columns: {available}"
                )

        for row in reader:
            raw = row.get(selected_column, "")
            category = normalize_category(raw)
            if category:
                counter[category] += 1

    print(f"Top {args.top} categories in column '{selected_column}':")
    for idx, (category, count) in enumerate(counter.most_common(args.top), start=1):
        print(f"{idx:>2}. {category} -> {count}")


if __name__ == "__main__":
    main()

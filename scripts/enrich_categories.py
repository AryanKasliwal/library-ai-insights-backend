#!/usr/bin/env python3
"""Enrich book categories using:
1. TF-IDF keyword extraction from descriptions (free)
2. LLM API for high-value books (optional, requires API key)
3. Title/Author-based heuristics as fallback

Usage:
  # Extract from descriptions only (fast, free)
  python scripts/enrich_categories.py --input app/data/csv/final_merged_books.csv --output app/data/csv/enriched_books.csv --method tfidf

  # With LLM enrichment (requires HUGGINGFACE_API_KEY)
  python scripts/enrich_categories.py --input app/data/csv/final_merged_books.csv --output app/data/csv/enriched_books.csv --method hybrid --llm-samples 5000
"""

import csv
import os
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import Counter
import re


class CategoryEnricher:
    """Enrich books with categories using multiple strategies."""
    
    # Genre keywords and heuristics
    GENRE_KEYWORDS = {
        "Fiction": ["novel", "story", "character", "plot", "narrative", "tale", "fiction"],
        "Science Fiction": ["future", "space", "alien", "sci-fi", "dystopian", "futuristic", "technology"],
        "Fantasy": ["magic", "wizard", "fantasy", "dragon", "enchant", "mythical", "quest"],
        "Mystery": ["mystery", "detective", "crime", "secret", "murder", "investigation", "clue"],
        "Romance": ["love", "romance", "relationship", "passion", "heart", "couple", "beloved"],
        "Thriller": ["thriller", "suspense", "danger", "death", "murder", "action", "intense"],
        "History": ["history", "historical", "past", "era", "century", "ancient", "war"],
        "Biography": ["biography", "life story", "memoir", "autobiography", "personal", "journey"],
        "Self-Help": ["self-help", "improvement", "personal growth", "motivation", "development", "guide"],
        "Science": ["science", "research", "study", "experiment", "discovery", "theory", "physics", "biology"],
        "Business": ["business", "management", "economics", "finance", "trade", "entrepreneurship", "market"],
        "Technology": ["technology", "programming", "software", "computer", "digital", "internet", "code"],
        "Children": ["children", "kids", "young readers", "juvenile", "picture book", "fairy tale"],
        "Education": ["education", "learning", "teaching", "academic", "textbook", "course", "lesson"],
        "Philosophy": ["philosophy", "ethics", "morality", "thought", "wisdom", "belief", "existential"],
        "Art": ["art", "painting", "artist", "visual", "illustration", "creative", "design"],
        "Music": ["music", "song", "musician", "orchestra", "composer", "symphony", "audio"],
        "Travel": ["travel", "journey", "destination", "adventure", "exploration", "geography"],
        "Cooking": ["recipe", "cooking", "food", "cuisine", "chef", "culinary", "kitchen"],
    }
    
    def __init__(self):
        self.genre_patterns = self._compile_patterns()
    
    def _compile_patterns(self) -> Dict[str, List[str]]:
        """Compile keyword patterns for each genre."""
        return self.GENRE_KEYWORDS
    
    def extract_categories_from_text(self, text: str, title: str = "", authors: str = "") -> List[str]:
        """Extract categories from description using keyword matching."""
        if not text:
            return []
        
        # Combine text sources
        combined = f"{title} {text} {authors}".lower()
        
        # Score each genre
        scores = {}
        words = re.findall(r'\b\w+\b', combined)
        word_count = Counter(words)
        
        for genre, keywords in self.GENRE_KEYWORDS.items():
            score = sum(word_count.get(kw, 0) for kw in keywords)
            if score > 0:
                scores[genre] = score
        
        # Return top 3 genres
        top_genres = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
        return [g[0] for g in top_genres if g[1] > 0]
    
    def extract_from_description_tfidf(self, text: str) -> List[str]:
        """Extract key terms using simple TF-IDF-like approach."""
        if not text or len(text) < 50:
            return []
        
        # Common English stopwords
        stopwords = {
            'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
            'has', 'he', 'in', 'is', 'it', 'of', 'on', 'or', 'that', 'the',
            'this', 'to', 'was', 'will', 'with', 'i', 'you', 'we', 'they',
        }
        
        # Extract words
        words = re.findall(r'\b[a-z]{3,}\b', text.lower())
        # Remove stopwords and get frequencies
        filtered = [w for w in words if w not in stopwords]
        freq = Counter(filtered)
        
        # Return top 5 most frequent terms
        top_terms = [w for w, _ in freq.most_common(5)]
        return top_terms
    
    def load_books(self, csv_path: str) -> List[Dict]:
        """Load books from CSV."""
        books = []
        with open(csv_path, 'r', encoding='utf-8', errors='replace', newline='') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i % 50000 == 0:
                    print(f"  Loaded {i} books...")
                books.append(row)
        return books
    
    def enrich_with_tfidf(self, books: List[Dict]) -> List[Dict]:
        """Enrich categories using keyword extraction from descriptions."""
        print("Enriching categories with TF-IDF keyword extraction...")
        
        enriched = 0
        for i, book in enumerate(books):
            if i % 50000 == 0:
                print(f"  Processing {i}/{len(books)}...")
            
            # If categories already exist, skip
            if book.get('categories') and book['categories'].strip():
                continue
            
            # Try to extract from description
            description = book.get('description', '').strip()
            title = book.get('title', '').strip()
            authors = book.get('authors', '').strip()
            
            if description:
                # Use keyword matching first
                categories = self.extract_categories_from_text(description, title, authors)
                if categories:
                    book['categories'] = ','.join(categories)
                    enriched += 1
                else:
                    # Fallback: extract key terms
                    terms = self.extract_from_description_tfidf(description)
                    if terms:
                        book['categories'] = ','.join(terms)
                        enriched += 1
        
        print(f"✓ Enriched {enriched} books with TF-IDF")
        return books
    
    def enrich_with_llm(self, books: List[Dict], samples: int = 5000, model: str = "mistral") -> List[Dict]:
        """Enrich using open LLM API (Hugging Face).
        
        Requires HUGGINGFACE_API_KEY environment variable.
        Note: This is optional. TF-IDF already covers most needs.
        """
        try:
            import requests
        except ImportError:
            print("⚠ requests library not found. Install with: pip install requests")
            return books
        
        api_key = os.getenv("HUGGINGFACE_API_KEY")
        if not api_key:
            print("⚠ HUGGINGFACE_API_KEY not set. Skipping LLM enrichment.")
            print("  Set it with: export HUGGINGFACE_API_KEY=your_key")
            return books
        
        print(f"Enriching with LLM (top {samples} high-value books)...")
        
        # Select books to enrich: priority to high-rating, high-review books
        candidates = [
            b for b in books 
            if not b.get('categories') or not b['categories'].strip()
        ]
        
        # Sort by rating * review count
        candidates.sort(
            key=lambda b: (
                float(b.get('average_rating', 0)) * int(b.get('ratings_count', 0))
            ),
            reverse=True
        )
        
        # Take top samples
        to_enrich = candidates[:min(samples, len(candidates))]
        print(f"  Found {len(to_enrich)} high-value books to enrich")
        
        headers = {"Authorization": f"Bearer {api_key}"}
        api_url = f"https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.1"
        
        enriched_count = 0
        for i, book in enumerate(to_enrich):
            if i % 100 == 0:
                print(f"  Enriched {i}/{len(to_enrich)}...")
            
            title = book.get('title', 'Unknown').strip()
            description = book.get('description', '').strip()
            text = f"Title: {title}\nDescription: {description[:300]}"
            
            prompt = f"""Given this book:
{text}

List 3-5 relevant genres or categories (comma-separated, no quotes):"""
            
            try:
                response = requests.post(
                    api_url,
                    headers=headers,
                    json={"inputs": prompt, "max_new_tokens": 50},
                    timeout=10
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result and isinstance(result, list) and len(result) > 0:
                        generated_text = result[0].get('generated_text', '')
                        # Extract the categories part
                        if ':' in generated_text:
                            categories = generated_text.split(':')[-1].strip()
                            # Clean up
                            categories = re.sub(r'["\']', '', categories)
                            categories = re.sub(r'\*\*', '', categories)
                            book['categories'] = categories
                            enriched_count += 1
            except Exception as e:
                if i == 0:
                    print(f"  Note: LLM API error (may be rate limited or invalid key): {e}")
        
        print(f"✓ Enriched {enriched_count} books with LLM")
        return books
    
    def save_books(self, books: List[Dict], output_path: str):
        """Save enriched books to CSV."""
        if not books:
            print("No books to save")
            return
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Get all fieldnames from first book
        fieldnames = list(books[0].keys())
        
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(books)
        
        print(f"✓ Saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Enrich book categories")
    parser.add_argument('--input', required=True, help='Input CSV path')
    parser.add_argument('--output', required=True, help='Output CSV path')
    parser.add_argument(
        '--method',
        choices=['tfidf', 'hybrid'],
        default='tfidf',
        help='Enrichment method (tfidf=fast & free, hybrid=tfidf+optional LLM)'
    )
    parser.add_argument(
        '--llm-samples',
        type=int,
        default=5000,
        help='Number of books to enrich with LLM (in hybrid mode)'
    )
    parser.add_argument(
        '--llm-model',
        choices=['mistral', 'llama'],
        default='mistral',
        help='LLM model to use'
    )
    
    args = parser.parse_args()
    
    enricher = CategoryEnricher()
    
    print(f"Loading books from {args.input}...")
    books = enricher.load_books(args.input)
    print(f"✓ Loaded {len(books)} books")
    
    # TF-IDF enrichment (fast, always run)
    books = enricher.enrich_with_tfidf(books)
    
    # Optional LLM enrichment
    if args.method == 'hybrid':
        books = enricher.enrich_with_llm(books, samples=args.llm_samples, model=args.llm_model)
    
    # Check coverage
    with_cats = sum(1 for b in books if b.get('categories') and b['categories'].strip())
    print(f"\nCategory Coverage:")
    print(f"  Books with categories: {with_cats}/{len(books)} ({100*with_cats/len(books):.1f}%)")
    
    # Save
    enricher.save_books(books, args.output)


if __name__ == '__main__':
    main()

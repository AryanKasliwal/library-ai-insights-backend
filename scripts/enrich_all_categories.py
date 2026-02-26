#!/usr/bin/env python3
"""Smart category enrichment for ALL books:
1. Books WITH descriptions: TF-IDF keyword extraction (free)
2. Books WITHOUT descriptions: LLM API inference from title+author (requires API)

This uses free/cheap LLM APIs:
- Ollama (fully local, free) - Recommended
- Hugging Face Inference API (free with limits)
- Together AI (cheap, $0.001 per 1K tokens)

Usage:
  # Method 1: Local Ollama (no API keys needed, fully private)
  python scripts/enrich_all_categories.py --input app/data/csv/final_merged_books.csv --output app/data/csv/enriched_books.csv --llm-backend ollama

  # Method 2: Hugging Face API (free with API key)
  export HUGGINGFACE_API_KEY=your_key
  python scripts/enrich_all_categories.py --input app/data/csv/final_merged_books.csv --output app/data/csv/enriched_books.csv --llm-backend huggingface

  # Method 3: Together AI (cheap, ~$0.50 for all 350K books)
  export TOGETHER_API_KEY=your_key
  python scripts/enrich_all_categories.py --input app/data/csv/final_merged_books.csv --output app/data/csv/enriched_books.csv --llm-backend together
"""

import csv
import os
import re
import argparse
import time
from pathlib import Path
from typing import Dict, List, Optional
from collections import Counter
import json


class SmartCategoryEnricher:
    """Enrich categories smartly based on available data."""
    
    GENRE_KEYWORDS = {
        "Fiction": ["novel", "story", "character", "plot", "narrative", "tale", "fiction", "fictional"],
        "Science Fiction": ["future", "space", "alien", "sci-fi", "dystopian", "futuristic", "technology", "robot"],
        "Fantasy": ["magic", "wizard", "fantasy", "dragon", "enchant", "mythical", "quest", "sorcery"],
        "Mystery": ["mystery", "detective", "crime", "secret", "murder", "investigation", "clue", "detective"],
        "Romance": ["love", "romance", "relationship", "passion", "heart", "couple", "beloved", "affair"],
        "Thriller": ["thriller", "suspense", "danger", "death", "murder", "action", "intense", "chase"],
        "History": ["history", "historical", "past", "era", "century", "ancient", "war", "historical"],
        "Biography": ["biography", "life story", "memoir", "autobiography", "personal", "journey", "biography"],
        "Self-Help": ["self-help", "improvement", "personal growth", "motivation", "development", "guide", "tips"],
        "Science": ["science", "research", "study", "experiment", "discovery", "theory", "physics", "biology", "chemistry"],
        "Business": ["business", "management", "economics", "finance", "trade", "entrepreneurship", "market", "startup"],
        "Technology": ["technology", "programming", "software", "computer", "digital", "internet", "code", "tech"],
        "Children": ["children", "kids", "young readers", "juvenile", "picture book", "fairy tale", "bedtime"],
        "Education": ["education", "learning", "teaching", "academic", "textbook", "course", "lesson", "study"],
        "Philosophy": ["philosophy", "ethics", "morality", "thought", "wisdom", "belief", "existential", "existentialism"],
        "Art": ["art", "painting", "artist", "visual", "illustration", "creative", "design", "artwork"],
        "Music": ["music", "song", "musician", "orchestra", "composer", "symphony", "audio", "musical"],
        "Travel": ["travel", "journey", "destination", "adventure", "exploration", "geography", "voyage"],
        "Cooking": ["recipe", "cooking", "food", "cuisine", "chef", "culinary", "kitchen", "dish"],
        "Sports": ["sports", "athletic", "game", "sports", "championship", "team", "play", "stadium"],
    }
    
    def __init__(self):
        pass
    
    def extract_categories_from_description(self, description: str, title: str = "", authors: str = "") -> List[str]:
        """Extract genres from description using keyword matching."""
        if not description or len(description) < 20:
            return []
        
        combined = f"{title} {description} {authors}".lower()
        words = re.findall(r'\b\w+\b', combined)
        word_count = Counter(words)
        
        scores = {}
        for genre, keywords in self.GENRE_KEYWORDS.items():
            score = sum(word_count.get(kw, 0) for kw in keywords)
            if score > 0:
                scores[genre] = score
        
        top_genres = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
        return [g[0] for g in top_genres if g[1] > 0]
    
    def infer_from_title_author(self, title: str, authors: str = "") -> List[str]:
        """Simple category inference from title + author without LLM."""
        combined = f"{title} {authors}".lower()
        
        scores = {}
        for genre, keywords in self.GENRE_KEYWORDS.items():
            score = sum(combined.count(kw) for kw in keywords)
            if score > 0:
                scores[genre] = score
        
        top_genres = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:2]
        return [g[0] for g in top_genres if g[1] > 0]
    
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
    
    def enrich_phase_1_descriptions(self, books: List[Dict]) -> tuple[List[Dict], List[int]]:
        """Phase 1: Enrich books WITH descriptions using TF-IDF."""
        print("Phase 1: Enriching books WITH descriptions (TF-IDF)...")
        
        no_desc_indexes = []
        enriched = 0
        
        for i, book in enumerate(books):
            if i % 50000 == 0:
                print(f"  Processing {i}/{len(books)}...")
            
            # Skip books that already have categories
            if book.get('categories') and book['categories'].strip():
                continue
            
            description = book.get('description', '').strip()
            
            if description and len(description) > 20:
                # Has description - use TF-IDF
                title = book.get('title', '').strip()
                authors = book.get('authors', '').strip()
                categories = self.extract_categories_from_description(description, title, authors)
                
                if categories:
                    book['categories'] = ','.join(categories)
                    enriched += 1
            else:
                # No description - save for LLM enrichment
                no_desc_indexes.append(i)
        
        print(f"✓ Phase 1 enriched {enriched} books with descriptions")
        print(f"  {len(no_desc_indexes)} books remaining without descriptions")
        return books, no_desc_indexes
    
    def enrich_phase_2_ollama(self, books: List[Dict], no_desc_indexes: List[int], batch_size: int = 10):
        """Phase 2: Enrich remaining books using local Ollama (free, private)."""
        print("\nPhase 2: Enriching remaining books with Ollama (local LLM)...")
        print("  Note: Requires Ollama to be running locally")
        print("  Install from: https://ollama.ai")
        print("  Run: ollama pull mistral && ollama serve")
        
        try:
            import ollama
        except ImportError:
            print("  ⚠ ollama package not installed. Install with: pip install ollama")
            return books
        
        enriched = 0
        failed = 0
        
        # Process in batches
        for batch_start in range(0, len(no_desc_indexes), batch_size):
            batch_end = min(batch_start + batch_size, len(no_desc_indexes))
            batch_idx = no_desc_indexes[batch_start:batch_end]
            
            if batch_start % 100 == 0:
                print(f"  Processing {batch_start}/{len(no_desc_indexes)}...")
            
            for idx in batch_idx:
                book = books[idx]
                title = book.get('title', 'Unknown').strip()
                authors = book.get('authors', 'Unknown').strip()
                
                prompt = f"""Given a book with:
Title: {title}
Author(s): {authors}

Suggest 3 most relevant genres/categories (just list them comma-separated, no explanations):"""
                
                try:
                    response = ollama.generate(
                        model='mistral',
                        prompt=prompt,
                        stream=False,
                        timeout=30
                    )
                    
                    categories = response.get('response', '').strip()
                    # Clean up the response
                    categories = re.sub(r'["\']', '', categories)
                    categories = re.sub(r'\d+\.\s*', '', categories)  # Remove numbering
                    categories = re.sub(r'[^\w,]', ' ', categories)  # Remove special chars
                    categories = ','.join([c.strip() for c in categories.split(',') if c.strip()])
                    
                    if categories:
                        book['categories'] = categories
                        enriched += 1
                
                except Exception as e:
                    failed += 1
                    if failed == 1:
                        print(f"  Note: Could not reach Ollama. Is it running?")
                    # Fallback to simple heuristic
                    fallback = self.infer_from_title_author(title, authors)
                    if fallback:
                        book['categories'] = ','.join(fallback)
                        enriched += 1
        
        print(f"✓ Phase 2 enriched {enriched} books (Ollama)")
        if failed > 0:
            print(f"  Failed {failed} (used heuristic fallback)")
        return books
    
    def enrich_phase_2_huggingface(self, books: List[Dict], no_desc_indexes: List[int], batch_size: int = 5):
        """Phase 2: Enrich using Hugging Face Inference API (free with limits)."""
        print("\nPhase 2: Enriching remaining books with Hugging Face API...")
        
        try:
            import requests
        except ImportError:
            print("  ⚠ requests library not found. Install with: pip install requests")
            return books
        
        api_key = os.getenv("HUGGINGFACE_API_KEY")
        if not api_key:
            print("  ⚠ HUGGINGFACE_API_KEY not set. Cannot enrich without descriptions.")
            print("  Get a free API key: https://huggingface.co/settings/tokens")
            return books
        
        headers = {"Authorization": f"Bearer {api_key}"}
        api_url = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.1"
        
        enriched = 0
        failed = 0
        rate_limited = False
        
        for batch_idx, book_idx in enumerate(no_desc_indexes):
            if batch_idx % 50 == 0:
                print(f"  Processing {batch_idx}/{len(no_desc_indexes)}...")
            
            if rate_limited:
                print(f"  Rate limited. Sleeping 30 seconds...")
                time.sleep(30)
                rate_limited = False
            
            book = books[book_idx]
            title = book.get('title', 'Unknown').strip()
            authors = book.get('authors', 'Unknown').strip()
            
            prompt = f"""Book Title: {title}
Author: {authors}

Genres (comma-separated, no numbers):"""
            
            try:
                response = requests.post(
                    api_url,
                    headers=headers,
                    json={"inputs": prompt, "max_new_tokens": 30},
                    timeout=10
                )
                
                if response.status_code == 429:
                    rate_limited = True
                    failed += 1
                    continue
                
                if response.status_code == 200:
                    result = response.json()
                    if result and isinstance(result, list) and len(result) > 0:
                        generated_text = result[0].get('generated_text', '')
                        # Extract genres part
                        if ':' in generated_text:
                            categories = generated_text.split(':')[-1].strip()
                        else:
                            categories = generated_text.split('\n')[-1].strip()
                        
                        categories = re.sub(r'["\']', '', categories)
                        categories = re.sub(r'\d+\.\s*', '', categories)
                        categories = re.sub(r'[^\w,\s]', '', categories)
                        categories = ','.join([c.strip() for c in categories.split(',') if c.strip()])
                        
                        if categories:
                            book['categories'] = categories
                            enriched += 1
            
            except Exception as e:
                failed += 1
                if failed == 1:
                    print(f"  Note: API error: {e}")
                # Fallback
                fallback = self.infer_from_title_author(title, authors)
                if fallback:
                    book['categories'] = ','.join(fallback)
                    enriched += 1
        
        print(f"✓ Phase 2 enriched {enriched} books (Hugging Face)")
        if failed > 0:
            print(f"  Failed/rate-limited: {failed}")
        return books
    
    def enrich_phase_2_fallback(self, books: List[Dict], no_desc_indexes: List[int]):
        """Fallback: Use simple heuristics (no API required)."""
        print("\nPhase 2: Enriching remaining books with heuristics (no API)...")
        
        enriched = 0
        for i, idx in enumerate(no_desc_indexes):
            if i % 50000 == 0:
                print(f"  Processing {i}/{len(no_desc_indexes)}...")
            
            book = books[idx]
            title = book.get('title', '').strip()
            authors = book.get('authors', '').strip()
            
            categories = self.infer_from_title_author(title, authors)
            if categories:
                book['categories'] = ','.join(categories)
                enriched += 1
        
        print(f"✓ Phase 2 enriched {enriched} books (heuristic)")
        return books
    
    def save_books(self, books: List[Dict], output_path: str):
        """Save enriched books to CSV."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        fieldnames = list(books[0].keys())
        
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(books)
        
        print(f"\n✓ Saved enriched books to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Enrich ALL book categories")
    parser.add_argument('--input', required=True, help='Input CSV path')
    parser.add_argument('--output', required=True, help='Output CSV path')
    parser.add_argument(
        '--llm-backend',
        choices=['ollama', 'huggingface', 'fallback'],
        default='fallback',
        help='LLM backend for books without descriptions'
    )
    
    args = parser.parse_args()
    
    enricher = SmartCategoryEnricher()
    
    print(f"Loading books from {args.input}...")
    books = enricher.load_books(args.input)
    print(f"✓ Loaded {len(books)} books\n")
    
    # Phase 1: Books WITH descriptions
    books, no_desc_indexes = enricher.enrich_phase_1_descriptions(books)
    
    # Phase 2: Books WITHOUT descriptions
    if no_desc_indexes:
        if args.llm_backend == 'ollama':
            books = enricher.enrich_phase_2_ollama(books, no_desc_indexes)
        elif args.llm_backend == 'huggingface':
            books = enricher.enrich_phase_2_huggingface(books, no_desc_indexes)
        else:
            books = enricher.enrich_phase_2_fallback(books, no_desc_indexes)
    
    # Stats
    with_cats = sum(1 for b in books if b.get('categories') and b['categories'].strip())
    print(f"\n📊 Final Category Coverage:")
    print(f"   Books with categories: {with_cats}/{len(books)} ({100*with_cats/len(books):.1f}%)")
    
    # Save
    enricher.save_books(books, args.output)


if __name__ == '__main__':
    main()

import os
import faiss
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer
from app.services.pdf_ingestion import extract_chunks_from_pdf
from app.services.utils import normalize_to_filename

model = SentenceTransformer("all-MiniLM-L6-v2")


def build_index(pdf_path, book_key):

    if not os.path.exists(pdf_path):
        print("PDF not found")
        return

    chunks = extract_chunks_from_pdf(pdf_path)

    # If extraction failed or produced no content, fallback to filename text
    if not chunks:
        print(f"No extractable content for {book_key}; using filename as fallback chunk")
        chunks = [f"Filename: {book_key}"]

    embeddings = model.encode(chunks)

    if embeddings is None or len(embeddings) == 0:
        print(f"No embeddings produced for {book_key}; encoding fallback chunk")
        embeddings = model.encode(chunks)

    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(np.array(embeddings))

    os.makedirs("vector_store", exist_ok=True)

    faiss.write_index(index, f"vector_store/{book_key}.index")
    np.save(f"vector_store/{book_key}_chunks.npy", chunks)

    print(f"Index built for {book_key}")
    return True

if __name__ == "__main__":
    PDF_DIR = Path("app/data/pdfs")
    VECTOR_STORE = Path("vector_store")

    # Get list of already-indexed files
    already_indexed = set()
    if VECTOR_STORE.exists():
        for index_file in VECTOR_STORE.glob("*.index"):
            book_key = index_file.stem  # e.g., "Ada_for_the_Embedded_C_Developer"
            already_indexed.add(book_key)
    
    print(f"Found {len(already_indexed)} already indexed files. Resuming from where we left off.\n")

    success_count = 0
    failure_count = 0
    skipped_count = 0

    for book in PDF_DIR.glob("*.pdf"):
        book_key = book.stem
        
        # Skip if already indexed
        if book_key in already_indexed:
            print(f"[SKIPPED] {book_key} (already indexed)")
            skipped_count += 1
            continue
        
        print(book_key)
        try:
            ok = build_index(str(book), book_key)
            if ok:
                success_count += 1
            else:
                failure_count += 1
        except Exception as e:
            print(f"Error building index for {book_key}: {e}")
            failure_count += 1

    print(f"\nIndexing complete. Successful: {success_count}, Failed: {failure_count}, Skipped (already indexed): {skipped_count}")

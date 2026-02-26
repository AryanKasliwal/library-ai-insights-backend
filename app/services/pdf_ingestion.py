import io
import re
import zipfile
from pypdf import PdfReader, errors


def clean_text(text):
    """
    Normalize whitespace and clean extracted text.
    """
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_text_from_reader(reader, skip_pages=3):
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"

    text = clean_text(text)

    # Remove front matter before first chapter
    chapter_patterns = [
        r"CHAPTER\s+I",
        r"\nI\.\s",
        r"\nI\s"
    ]

    for pattern in chapter_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            text = text[match.start():]
            break

    return text


def _chunk_text(text, chunk_size=800, overlap=150):
    """
    Sentence-based chunking with overlap.
    """
    sentences = re.split(r'(?<=[.!?]) +', text)

    chunks = []
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) + len(sentence) <= chunk_size:
            current_chunk += " " + sentence
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk.strip())

    # Add overlap
    final_chunks = []
    for i in range(len(chunks)):
        chunk = chunks[i]
        if i > 0:
            overlap_text = chunks[i - 1][-overlap:]
            chunk = overlap_text + " " + chunk
        final_chunks.append(chunk.strip())

    return final_chunks


def extract_chunks_from_pdf(path, chunk_size=800, overlap=150):
    """
    Extract text from PDF with recovery logic,
    clean it, and return smart semantic chunks.
    """

    # Attempt 1: normal read
    try:
        reader = PdfReader(path)
        text = _extract_text_from_reader(reader)

        if text:
            return _chunk_text(text, chunk_size, overlap)

    except Exception:
        pass

    # Attempt 2: raw bytes recovery
    try:
        with open(path, "rb") as f:
            data = f.read()
    except Exception:
        return []

    pdf_sig = b"%PDF-"
    idx = data.find(pdf_sig)

    if idx != -1:
        try:
            bio = io.BytesIO(data[idx:])
            reader = PdfReader(bio)
            text = clean_text(_extract_text_from_reader(reader, skip_pages=0))
            if text:
                return _chunk_text(text, chunk_size, overlap)
        except Exception:
            pass

        # Try appending EOF marker
        try:
            bio = io.BytesIO(data[idx:] + b"\n%%EOF")
            reader = PdfReader(bio)
            text = clean_text(_extract_text_from_reader(reader, skip_pages=0))
            if text:
                return _chunk_text(text, chunk_size, overlap)
        except Exception:
            pass

    # Attempt 3: ZIP container
    try:
        if data.startswith(b"PK"):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for name in z.namelist():
                    if name.lower().endswith(".pdf"):
                        try:
                            entry = z.read(name)
                            bio = io.BytesIO(entry)
                            reader = PdfReader(bio)
                            text = clean_text(_extract_text_from_reader(reader, skip_pages=0))
                            if text:
                                return _chunk_text(text, chunk_size, overlap)
                        except Exception:
                            continue
    except Exception:
        pass

    return []

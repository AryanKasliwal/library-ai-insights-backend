import re

def normalize_to_filename(title: str) -> str:
    """
    Converts book title to filesystem-safe pdf filename.
    Example:
    'Thinking, Fast and Slow' -> thinking_fast_and_slow
    """
    title = title.lower()
    title = re.sub(r"[^\w\s]", "", title)  # remove punctuation
    title = re.sub(r"\s+", "_", title)     # replace spaces with underscore
    return title.strip("_")

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import os

class RAGService:
    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")

    def load_index(self, book_id):
        index_path = f"vector_store/{book_id}.index"
        chunks_path = f"vector_store/{book_id}_chunks.npy"

        if not os.path.exists(index_path):
            return None, None

        index = faiss.read_index(index_path)
        chunks = np.load(chunks_path, allow_pickle=True)

        return index, chunks

    def query(self, book_id, question, k=3):
        index, chunks = self.load_index(book_id)

        if index is None:
            return None

        q_embedding = self.model.encode([question])
        distances, indices = index.search(np.array(q_embedding), k)

        results = [chunks[i] for i in indices[0]]

        return results


rag_service = RAGService()

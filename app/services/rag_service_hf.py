import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from huggingface_hub import InferenceClient
import os
import re
import warnings
from dotenv import load_dotenv
from app.services.utils import normalize_to_filename

load_dotenv()

warnings.filterwarnings(
    "ignore",
    message="`resume_download` is deprecated",
    category=FutureWarning,
)

class RAGServiceHF:
    def __init__(self):
        self.model = None
        self.llm = InferenceClient(
            token=os.environ.get("HF_READ_KEY"),
            model="openai/gpt-oss-20b"
        )

    def _get_embedding_model(self):
        if self.model is None:
            self.model = SentenceTransformer("all-MiniLM-L6-v2")
        return self.model

    def load_index(self, book_id):
        index_path = f"vector_store/{book_id}.index"
        chunks_path = f"vector_store/{book_id}_chunks.npy"

        if not os.path.exists(index_path) or not os.path.exists(chunks_path):
            return None, None

        index = faiss.read_index(index_path)
        chunks = np.load(chunks_path, allow_pickle=True)
        return index, chunks

    def _length_instruction(self, question):
        q = question.lower()
        minute_match = re.search(r"(\d+)\s*(min|mins|minute|minutes)\b", q)
        word_match = re.search(r"(\d{2,4})\s*(word|words)\b", q)

        if minute_match:
            minutes = int(minute_match.group(1))
            min_words = minutes * 150
            return f"If the user asks for a {minutes}-minute summary, write at least {min_words} words."

        if word_match:
            target_words = int(word_match.group(1))
            return f"Write around {target_words} words (minimum {max(80, int(target_words * 0.9))} words)."

        if any(token in q for token in ["brief", "short", "quick", "concise"]):
            return "Keep the response concise: 120-220 words."

        return "Give a well-explained response with enough detail: 250-450 words."

    def _source_cap_from_answer(self, answer_text):
        words = len((answer_text or "").split())
        if words < 140:
            return 2
        if words < 260:
            return 3
        if words < 420:
            return 4
        if words < 650:
            return 5
        if words < 950:
            return 6
        return 7

    def _filter_by_llm_relevance(self, question, chunks_with_indices):
        """Use LLM to evaluate which chunks are ESSENTIAL to answer the question.
        Prefer fewer, higher-quality references over many mediocre ones."""
        if not chunks_with_indices:
            return []

        # Build evaluation prompt with stricter criteria
        chunks_text = "\n\n".join(
            f"[CHUNK {i}]\n{c['text']}"
            for i, c in enumerate(chunks_with_indices)
        )

        eval_prompt = f"""You are selecting ESSENTIAL book excerpts to answer a user question.
Quality over quantity: Return only chunks truly necessary to answer the question.
Prefer fewer, high-quality chunks over many mediocre ones.

Question: {question}

Below are potential excerpts. For each, decide if it is ESSENTIAL to answering the question.
Return ONLY a Python list of at most 7 chunk indices that are essential. Example: [0, 2, 4]
If fewer than 3 chunks are essential, return just those. Example: [1]
If no chunks are essential, return an empty list: []

--- EXCERPTS ---
{chunks_text}

--- RESPONSE (Python list only, no other text) ---"""

        try:
            messages = [{"role": "user", "content": eval_prompt}]
            response = self.llm.chat_completion(messages, max_tokens=100)
            response_text = response.choices[0].message.content.strip()
            # Parse the list from the response
            import ast
            relevant_indices = ast.literal_eval(response_text)
            if not isinstance(relevant_indices, list):
                relevant_indices = []
            # Cap at 7 as a safety limit
            relevant_indices = relevant_indices[:7]
        except Exception as e:
            print(f"Warning: LLM relevance filter failed: {e}, returning top 3 chunks")
            # Fallback: return only top 3 chunks if filter fails
            relevant_indices = list(range(min(3, len(chunks_with_indices))))

        # Return only the relevant chunks
        return [chunks_with_indices[i] for i in relevant_indices if i < len(chunks_with_indices)]

    def search_chunks(self, question, index, chunks, k=20):
        q_embedding = self._get_embedding_model().encode([question])
        distances, indices = index.search(np.array(q_embedding), k)

        results = []
        for idx in indices[0]:
            if idx == -1:
                continue
            chunk = chunks[idx]
            if isinstance(chunk, dict):
                results.append({
                    "text": chunk.get("text", ""),
                    "page": chunk.get("page", None),
                })
            else:
                results.append({
                    "text": str(chunk),
                    "page": None,
                })
        return results

    def build_prompt(self, book_name, chat_history, context_chunks, question):
        context_text = "\n\n".join(
            f"[Page {c['page']}]\n{c['text']}" if c['page'] else c['text']
            for c in context_chunks
        )

        history_text = ""
        if chat_history:
            history_lines = []
            for msg in chat_history[-10:]:
                role = "User" if msg["role"] == "user" else "Assistant"
                history_lines.append(f"{role}: {msg['message']}")
            history_text = "\n".join(history_lines)

        length_instruction = self._length_instruction(question)

        return f"""You are a research assistant helping a user understand the book "{book_name}".
            Answer the user's question based ONLY on the provided book excerpts below and the chat history.
            If the answer is not found in the excerpts and chat history, say so clearly.
            Be accurate and directly address the user's intent.
            Use the conversation history to interpret follow-up questions and references like "this", "that", or "as discussed earlier".
            If earlier chat messages provide needed context, explicitly incorporate that context into the answer.
            {length_instruction}

            Writing rules:
            - Do NOT mention page numbers, excerpt labels, source counts, or phrases like "as highlighted on page...".
            - Do NOT reference the retrieval process (no "based on the excerpts above" in the final answer).
            - Present the answer as clean factual prose tailored to the request.

            --- BOOK EXCERPTS ---
            {context_text}

            --- CONVERSATION HISTORY ---
            {history_text if history_text else "No previous conversation."}

            --- QUESTION ---
            {question}

            --- ANSWER ---"""

    def query(self, book_id, question, chat_history=[], k=20):
        index, chunks = self.load_index(book_id)

        if index is None:
            return {
                "answer": f"No index found for '{book_id}'. This book may not have AI research enabled.",
                "sources": []
            }

        all_chunks = self.search_chunks(question, index, chunks, k)

        # Use LLM to filter for actual relevance
        relevant_chunks = self._filter_by_llm_relevance(question, all_chunks)

        if not relevant_chunks:
            return {
                "answer": "I couldn't find relevant content in this book for your question.",
                "sources": []
            }

        prompt = self.build_prompt(book_id, chat_history, relevant_chunks, question)

        try:
            messages = [{"role": "user", "content": prompt}]
            full_response = ""
            for msg in self.llm.chat_completion(
                messages,
                max_tokens=1024,
                stream=True,
            ):
                if msg.choices and msg.choices[0].delta.content:
                    full_response += msg.choices[0].delta.content
            answer = full_response
        except Exception as e:
            return {
                "answer": f"Error generating response: {str(e)}",
                "sources": []
            }


        sources = [
            {"text": c["text"], "page": c["page"]}
            for c in relevant_chunks
            if c["page"] is not None
        ]
        sources = sources[: self._source_cap_from_answer(answer)]

        return {
            "answer": answer,
            "sources": sources
        }


rag_service_hf = RAGServiceHF()
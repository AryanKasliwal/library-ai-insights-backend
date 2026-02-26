from app.services.rag_service import rag_service

book_key = "A_Princess_of_Mars"

question = "What is the main idea of the book?"

results = rag_service.query(book_key, question)

print("\nTop Results:\n")
for i, r in enumerate(results):
    print(f"\n--- Result {i+1} ---\n")
    print(r)

import pandas as pd
import os

def generate_metadata_csv():
    pdf_dir = "app/data/pdfs"
    csv_path = "app/data/books_metadata.csv"

    pdf_files = [f for f in os.listdir(pdf_dir) if f.endswith('.pdf')]

    data = []
    for pdf in pdf_files:
        title = pdf.replace('.pdf', '').replace('_', ' ')
        data.append({
            'bookID': pdf.replace('.pdf', ''),  # Use filename without .pdf as bookID
            'title': title,
            'authors': ''
        })

    df = pd.DataFrame(data)
    df.to_csv(csv_path, index=False)
    print(f"Generated metadata for {len(pdf_files)} books")

if __name__ == "__main__":
    generate_metadata_csv()
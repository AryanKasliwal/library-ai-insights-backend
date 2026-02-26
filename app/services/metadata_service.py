import pandas as pd

class MetadataService:
    def __init__(self, path="app/data/books_metadata.csv"):
        try:
            # Specify dtypes to avoid dtype issues
            self.df = pd.read_csv(path, dtype={"bookID": str, "title": str, "authors": str})
            self.df.fillna("", inplace=True)
        except pd.errors.EmptyDataError:
            # Create empty dataframe with expected columns if file is empty
            self.df = pd.DataFrame(columns=["bookID", "title", "authors"])
        except FileNotFoundError:
            # Create empty dataframe if file doesn't exist
            self.df = pd.DataFrame(columns=["bookID", "title", "authors"])

    def search_books(self, query: str):
        mask = (
            self.df["title"].str.contains(query, case=False) |
            self.df["authors"].str.contains(query, case=False)
        )
        return self.df[mask].head(50).to_dict(orient="records")

    def get_book(self, book_id: str):
        book = self.df[self.df["bookID"] == book_id]
        if book.empty:
            return None
        return book.iloc[0].to_dict()


metadata_service = MetadataService()

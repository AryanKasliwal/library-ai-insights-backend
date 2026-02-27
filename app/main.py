from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.api import books_api
# from app.api import rag  # TODO: Fix RAG service segfault
import os
import boto3
import tarfile
from dotenv import load_dotenv
load_dotenv()


def download_file_from_s3(filename):
    s3 = boto3.client(
        "s3",
        region_name=os.environ["AWS_REGION"],
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    )

    if not os.path.exists(filename):
        print(f"⬇️ Downloading {filename} from S3...")
        s3.download_file(
            os.environ["S3_BUCKET"],
            filename,
            filename
        )
        print(f"✅ {filename} downloaded.")


def download_vector_store():
    if os.path.exists("vector_store"):
        print("📦 Vector store already exists locally.")
        return

    print("⬇️ Downloading vector store from S3...")

    s3 = boto3.client(
        "s3",
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        region_name=os.environ["AWS_REGION"],
    )

    bucket = os.environ["S3_BUCKET"]

    s3.download_file(bucket, "vector_store.tar.gz", "vector_store.tar.gz")

    print("📂 Extracting vector store...")
    with tarfile.open("vector_store.tar.gz", "r:gz") as tar:
        tar.extractall()

    os.remove("vector_store.tar.gz")

    print("✅ Vector store ready.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup and shutdown."""
    # Startup
    print("\n🚀 Starting Library AI Insights Backend...")
    
    # Initialize book store with enriched data and recommendations
    from app.api.books_api import init_book_store
    try:
        download_file_from_s3("book_recommendations.json")
        download_vector_store()
        init_book_store(
            csv_path="app/data/csv/enriched_books_filtered.csv",
            recommendations_path="app/services/book_recommendations.json"
        )
        print("✅ BookStore initialized successfully")
    except Exception as e:
        print(f"⚠️ Warning: Could not load recommendations: {e}")
        print("   Falling back to CSV-only mode (no precomputed recommendations)")
        init_book_store(csv_path="app/data/csv/enriched_books_filtered.csv")
    
    yield  # App runs here
    
    # Shutdown
    print("\n🛑 Shutting down Library AI Insights Backend...")


app = FastAPI(
    title="Library AI Insights Backend",
    description="RAG system for library book search and recommendations",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",      # React dev server
        "http://localhost:5173",      # Vite dev server
        "http://localhost:8080",      # Alternative dev server
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
        "*",  # Allow all origins (for development only; restrict in production)
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include routers
app.include_router(books_api.router, prefix="/books", tags=["Books"])
# app.include_router(rag.router, prefix="/rag", tags=["RAG"])  # TODO: Fix RAG service imports


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "library-ai-insights"}

# Allow HEAD requests for /health (for monitoring compatibility)
@app.head("/health")
def health_head():
    return {"status": "ok", "service": "library-ai-insights"}

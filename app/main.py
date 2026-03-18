from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.api import books_api
import os
import boto3
from dotenv import load_dotenv
from app.services.cache_manager import start_cleanup_scheduler
load_dotenv()

def _get_s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        region_name=os.environ["AWS_REGION"],
    )

def download_file_from_s3(filename):
    s3 = _get_s3_client()
    if not os.path.exists(filename):
        print(f"⬇️ Downloading {filename} from S3...")
        s3.download_file(os.environ["S3_BUCKET"], filename, filename)
        print(f"✅ {filename} downloaded.")

def download_csv_from_s3():
    csv_path = "app/data/csv/enriched_books_filtered.csv"
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    if os.path.exists(csv_path):
        size_mb = os.path.getsize(csv_path) / (1024 * 1024)
        print(f"📊 Books CSV already exists locally ({size_mb:.1f} MB).")
        return
    print("⬇️ Downloading enriched books CSV from S3...")
    s3 = _get_s3_client()
    try:
        s3.download_file(os.environ["S3_BUCKET"], "enriched_books_filtered.csv", csv_path)
        size_mb = os.path.getsize(csv_path) / (1024 * 1024)
        print(f"✅ Books CSV downloaded ({size_mb:.1f} MB).")
    except Exception as e:
        print(f"❌ Failed to download CSV from S3: {e}")
        raise

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n🚀 Starting Library AI Insights Backend...")
    from app.api.books_api import init_book_store
    start_cleanup_scheduler()
    try:
        download_csv_from_s3()
        download_file_from_s3("book_recommendations.json")
        download_file_from_s3("book_list.json")
        init_book_store(
            csv_path="app/data/csv/enriched_books_filtered.csv",
            recommendations_path="book_recommendations.json"
        )
        print("✅ BookStore initialized successfully")
    except Exception as e:
        print(f"❌ Fatal Error: Could not initialize BookStore: {e}")
        raise

    yield
    print("\n🛑 Shutting down Library AI Insights Backend...")


app = FastAPI(
    title="Library AI Insights Backend",
    description="RAG system for library book search and recommendations",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(books_api.router, prefix="/books", tags=["Books"])

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "library-ai-insights"}

@app.head("/health")
def health_head():
    return {"status": "ok", "service": "library-ai-insights"}
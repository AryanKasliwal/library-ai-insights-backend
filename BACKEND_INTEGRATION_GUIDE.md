# Backend Integration Guide for Library AI Insights Frontend

This guide provides all information needed to integrate the LibraryInsights frontend with the backend API.

---

## Backend Overview

**Location:** `library-ai-insights-backend` (parent folder)  
**API Base URL:** `http://localhost:8000` (dev) | `http://backend.example.com` (production)  
**Framework:** FastAPI + Python  
**Startup:** `python3 -c "from app.main import app; import uvicorn; uvicorn.run(app, host='0.0.0.0', port=8000)"`

---

## Architecture & User Flows

### Home Page → Search → Results → Book Detail

1. **Home Page**: User enters search query in search bar
2. **Search Routing**: Frontend calls smart search endpoint with query
3. **Results Page**: Backend returns paginated results (10 per page)
4. **Pagination UI**: Display page numbers, first/last buttons
5. **Book Click**: User clicks book → frontend fetches full details
6. **Detail Page**: Display all book data (description, ratings, recommendations)

---

## API Endpoints

### 1. Smart Search (Home Page Search Bar)

**Endpoint:** `GET /books/search`

**Purpose:** Auto-detect search type (title/author/category) and return combined, ranked results

**Parameters:**
```
q (string, optional): Search query (any text). If omitted/blank, returns most recent books.
page (integer, optional): Page number (1-indexed), default=1
limit (integer, optional): Results per page, default=10, max=100
```

**Example:**
```bash
GET http://localhost:8000/books/search?q=python&page=1&limit=10
```

**Response:**
```json
{
  "query": "python",
  "search_type": "smart",
  "results": [
    {
      "found": true,
      "id": "0596007124",
      "isbn13": "0596007124",
      "isbn10": "0596007124",
      "title": "Learning Python",
      "author": "Mark Lutz",
      "publisher": "O'Reilly Media",
      "year": 2007,
      "year_str": "2007",
      "description": "...",
      "subjects": ["Programming", "Python"],
      "rating": 4.2,
      "ratingsCount": 342,
      "pages": "1236",
      "language": "eng",
      "thumbnail": "http://...",
      "thumbnails": {
        "small": "http://...",
        "medium": "http://...",
        "large": "http://..."
      },
      "available": true,
      "location": null,
      "callNumber": null
    },
    ... (9 more results)
  ],
  "pagination": {
    "page": 1,
    "limit": 10,
    "total": 342,
    "total_pages": 35,
    "has_next": true,
    "has_prev": false
  }
}
```

**Response Fields:**
- `query`: Echo of search query
- `search_type`: "smart" when a query is provided; "recent" when query is blank
- `resolved_category`: Corrected category label when typo-correction is applied (else `null`)
- `category_correction_applied`: `true` when query like `foction` is corrected to a real category like `fiction`
- `results`: Array of up to 10 books
- `pagination.total`: Total matching books across entire search
- `pagination.total_pages`: Max page number for this query
- `pagination.has_next`: Boolean for "next" button availability
- `pagination.has_prev`: Boolean for "previous" button availability

**Frontend Implementation:**
```javascript
const searchBooks = async (query, page = 1, limit = 10) => {
  const response = await fetch(
    `${API_BASE_URL}/books/search?q=${encodeURIComponent(query)}&page=${page}&limit=${limit}`
  );
  if (!response.ok) throw new Error('Search failed');
  return await response.json();
};

// Usage
const results = await searchBooks('python', 1, 10);
console.log(`Found ${results.pagination.total} books`);
console.log(`Showing page 1 of ${results.pagination.total_pages}`);
results.results.forEach(book => {
  console.log(`${book.title} by ${book.author}`);
});
```

---

### 2. Search by Title (Optional - Specific Type)

**Endpoint:** `GET /books/search/title`

**Purpose:** Search only in book titles (more specific than smart search)

**Parameters:**
```
q (string, required): Title search query
page (integer, optional): Page number, default=1
limit (integer, optional): Results per page, default=10
```

**Example:**
```bash
GET http://localhost:8000/books/search/title?q=harry+potter&page=1&limit=10
```

**Response:** Same structure as smart search (with `search_type: "title"`)

---

### 3. Search by Author (Optional - Specific Type)

**Endpoint:** `GET /books/search/author`

**Purpose:** Search only by author name

**Parameters:**
```
q (string, required): Author name
page (integer, optional): Page number, default=1
limit (integer, optional): Results per page, default=10
```

**Example:**
```bash
GET http://localhost:8000/books/search/author?q=J.K.%20Rowling&page=1&limit=10
```

---

### 4. Search by Category

**Endpoint:** `GET /books/search/category`

**Purpose:** Browse books by category (for "Search Catalog" button)

**Parameters:**
```
category (string, required): Category name (e.g., "Fiction", "Science", "Technology")
page (integer, optional): Page number, default=1
limit (integer, optional): Results per page, default=10
```

**Example:**
```bash
GET http://localhost:8000/books/search/category?category=Fiction&page=1&limit=10
```

---

### 5. Trending Books

**Endpoint:** `GET /books/trending`

**Purpose:** Get highest-rated books (for homepage showcase)

**Parameters:**
```
page (integer, optional): Page number, default=1
limit (integer, optional): Results per page, default=10
```

**Example:**
```bash
GET http://localhost:8000/books/trending?page=1&limit=20
```

---

### 6. Get Book Details (Click on Result)

**Endpoint:** `GET /books/{isbn}`

**Purpose:** Fetch complete details for a single book (detail page)

**Parameters:**
```
isbn (string, required): ISBN (can be ISBN10 or ISBN13)
```

**Example:**
```bash
GET http://localhost:8000/books/9780439785969
```

**Response:**
```json
{
  "found": true,
  "id": "9780439785969",
  "isbn13": "9780439785969",
  "isbn10": "0439785960",
  "title": "Harry Potter and the Prisoner of Azkaban",
  "author": "J.K. Rowling",
  "publisher": "Scholastic Inc.",
  "year": 1999,
  "year_str": "1999",
  "description": "Harry Potter, along with his best friends, Ron and Hermione...",
  "subjects": ["Fiction", "Fantasy", "Magic"],
  "rating": 4.56,
  "ratingsCount": 8234,
  "pages": "435",
  "language": "eng",
  "thumbnail": "http://images.amazon.com/...",
  "thumbnails": {
    "small": "http://...",
    "medium": "http://...",
    "large": "http://..."
  },
  "available": true,
  "location": null,
  "callNumber": null
}
```

**Error Response (Book Not Found):**
```json
{
  "found": false,
  "isbn": "9999999999",
  "message": "Book not found: 9999999999"
}
```

**Frontend Implementation:**
```javascript
const getBookDetails = async (isbn) => {
  const response = await fetch(`${API_BASE_URL}/books/${encodeURIComponent(isbn)}`);
  if (!response.ok) throw new Error('Failed to fetch book');
  const data = await response.json();
  
  if (!data.found) {
    throw new Error(`Book not found: ${data.message}`);
  }
  return data;
};

// Usage
const book = await getBookDetails('9780439785969');
if (book.found) {
  console.log(`${book.title} by ${book.author}`);
  console.log(`Rating: ${book.rating}/5 (${book.ratingsCount} reviews)`);
}
```

---

### 7. Get Similar Books (Recommendation Section)

**Endpoint:** `GET /books/{isbn}/similar`

**Purpose:** Get books similar to the current book (for "You May Also Like" section)

**Parameters:**
```
isbn (string, required): ISBN of reference book
limit (integer, optional): Number of recommendations, default=50, max=100
```

**Example:**
```bash
GET http://localhost:8000/books/9780439785969/similar?limit=10
```

**Response:**
```json
{
  "book": {
    "found": true,
    "id": "9780439785969",
    "title": "Harry Potter and the Prisoner of Azkaban",
    ...
  },
  "similar_books": [
    {
      "book": {
        "found": true,
        "id": "9780439135589",
        "title": "Harry Potter and the Goblet of Fire",
        ...
      },
      "similarity_score": 0.92
    },
    ...
  ],
  "total_similar": 10
}
```

**Frontend Implementation:**
```javascript
const getSimilarBooks = async (isbn, limit = 10) => {
  const response = await fetch(
    `${API_BASE_URL}/books/${encodeURIComponent(isbn)}/similar?limit=${limit}`
  );
  if (!response.ok) throw new Error('Failed to fetch similar books');
  return await response.json();
};
```

---

### 8. Get Statistics (Optional - Dashboard)

**Endpoint:** `GET /books/stats`

**Purpose:** Get library statistics (total books, coverage, etc.)

**Example:**
```bash
GET http://localhost:8000/books/stats
```

**Response:**
```json
{
  "total_isbn_entries": 118930,
  "unique_books": 110240,
  "books_with_recommendations": 95340,
  "books_with_categories": 110200,
  "authors_indexed": 24567,
  "categories_indexed": 892
}
```

---

### 9. Health Check

**Endpoint:** `GET /health`

**Purpose:** Verify backend is running

**Example:**
```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "ok",
  "service": "library-ai-insights"
}
```

---

## Pagination Guide

All search endpoints return pagination metadata:

```json
"pagination": {
  "page": 1,           // Current page number (1-indexed)
  "limit": 10,         // Results per page
  "total": 342,        // Total matching results
  "total_pages": 35,   // Ceiling(total / limit)
  "has_next": true,    // Can go to next page?
  "has_prev": false    // Can go to prev page?
}
```

**Frontend Pagination Template:**

```javascript
// Pagination buttons
const renderPagination = (pagination) => {
  const buttons = [];
  
  // First page button
  if (pagination.has_prev) {
    buttons.push(`<button onclick="goToPage(1)">« First</button>`);
  }
  
  // Previous button
  if (pagination.has_prev) {
    buttons.push(`<button onclick="goToPage(${pagination.page - 1})">‹ Prev</button>`);
  }
  
  // Page numbers (show pages 1-10 max)
  const maxPages = Math.min(pagination.total_pages, 10);
  for (let i = 1; i <= maxPages; i++) {
    const active = i === pagination.page ? ' active' : '';
    buttons.push(`<button class="page-num${active}" onclick="goToPage(${i})">${i}</button>`);
  }
  
  // Next button
  if (pagination.has_next) {
    buttons.push(`<button onclick="goToPage(${pagination.page + 1})">Next ›</button>`);
  }
  
  // Last page button
  if (pagination.has_next) {
    buttons.push(`<button onclick="goToPage(${pagination.total_pages})">Last »</button>`);
  }
  
  return buttons.join('\n');
};

// Handler function
const goToPage = async (pageNum) => {
  const results = await searchBooks(currentQuery, pageNum, 10);
  displayResults(results.results);
  displayPagination(results.pagination);
};
```

---

## Configuration

### Environment Variables

Set these in your frontend `.env` or config file:

```
REACT_APP_API_BASE_URL=http://localhost:8000
REACT_APP_API_TIMEOUT=10000
```

### API Configuration

```javascript
// src/config/api.js (or similar)
const API_CONFIG = {
  baseURL: process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000',
  timeout: parseInt(process.env.REACT_APP_API_TIMEOUT || '10000'),
  retryAttempts: 2,
  retryDelay: 1000,
};

export default API_CONFIG;
```

---

## Error Handling

### Book Not Found (instead of 404)

Instead of HTTP 404, the API returns 200 with `found: false`:

```javascript
const getBook = async (isbn) => {
  const response = await fetch(`${API_BASE_URL}/books/${isbn}`);
  const data = await response.json();
  
  if (!data.found) {
    // Handle "not found" gracefully
    showMessage(`Book ${isbn} not found in our catalog`);
    return null;
  }
  return data;
};
```

### Network Errors

```javascript
const searchWithRetry = async (query, maxRetries = 2) => {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await searchBooks(query, 1, 10);
    } catch (error) {
      console.error(`Attempt ${i + 1} failed:`, error);
      if (i < maxRetries - 1) {
        await new Promise(r => setTimeout(r, 1000 * (i + 1))); // Exponential backoff
      }
    }
  }
  showError('Unable to reach backend. Please try again.');
  return { results: [], pagination: { total: 0, total_pages: 0 } };
};
```

---

## Caching Strategy

### In-Memory Cache (Recommended)

```javascript
class BookCache {
  constructor(maxAge = 1 * 60 * 1000) { // 1 minute
    this.cache = new Map();
    this.maxAge = maxAge;
  }
  
  get(key) {
    const entry = this.cache.get(key);
    if (!entry) return null;
    if (Date.now() - entry.time > this.maxAge) {
      this.cache.delete(key);
      return null;
    }
    return entry.data;
  }
  
  set(key, data) {
    this.cache.set(key, { data, time: Date.now() });
  }
}

// Usage
const bookCache = new BookCache(5 * 60 * 1000); // 5 minute cache

const getBookWithCache = async (isbn) => {
  const cached = bookCache.get(`book_${isbn}`);
  if (cached) return cached;
  
  const book = await getBookDetails(isbn);
  bookCache.set(`book_${isbn}`, book);
  return book;
};
```

---

## CORS & Development

### Dev Server Proxy (Recommended for local development)

If backend doesn't have CORS enabled, add proxy to `package.json`:

```json
{
  "proxy": "http://localhost:8000",
  "devDependencies": {
    "http-proxy-middleware": "^2.0.0"
  }
}
```

Then create `src/setupProxy.js`:

```javascript
const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function(app) {
  app.use(
    '/books',
    createProxyMiddleware({
      target: 'http://localhost:8000',
      changeOrigin: true,
      pathRewrite: { '^/books': '/books' },
    })
  );
};
```

### Backend CORS (If backend needs to support CORS)

Add to `app/main.py`:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
```

---

## Testing Checklist

- [ ] Health check endpoint returns 200
- [ ] Smart search returns results with pagination
- [ ] Pagination metadata is correct (total_pages, has_next, has_prev)
- [ ] Book detail endpoint (GET /books/{isbn}) works
- [ ] Book not found returns `found: false` (not 404)
- [ ] Similar books endpoint returns recommendations
- [ ] Page navigation (first, prev, next, last) works correctly
- [ ] Search for non-existent book shows user-friendly message
- [ ] Network errors are handled gracefully

---

## Example Complete Flow

```javascript
// 1. User searches on home page
async function handleHomeSearch(query) {
  try {
    const results = await searchBooks(query, 1, 10);
    navigateToResults({ query, results });
  } catch (error) {
    showError('Search failed: ' + error.message);
  }
}

// 2. Results page - user clicks book
async function handleBookClick(isbn) {
  try {
    const book = await getBookDetails(isbn);
    if (!book.found) {
      showError(book.message);
      return;
    }
    navigateToDetail(book);
  } catch (error) {
    showError('Could not load book details');
  }
}

// 3. Detail page - load similar books
async function loadRecommendations(isbn) {
  try {
    const { similar_books } = await getSimilarBooks(isbn, 10);
    displayRecommendations(similar_books);
  } catch (error) {
    console.warn('Could not load recommendations:', error);
    // Gracefully degrade - show page without recommendations
  }
}

// 4. Results page - pagination
async function goToPage(query, pageNum) {
  try {
    const results = await searchBooks(query, pageNum, 10);
    displayResults(results.results);
    displayPagination(results.pagination);
    scrollToTop();
  } catch (error) {
    showError('Could not load page');
  }
}
```

---

## Deployment Notes

### Environment

- **Dev:** `API_BASE_URL=http://localhost:8000`
- **Staging:** `API_BASE_URL=https://api-staging.example.com`
- **Production:** `API_BASE_URL=https://api.example.com`

### Backend Startup (Production)

```bash
# Using Gunicorn (recommended for production)
gunicorn -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 app.main:app

# Using Docker
docker run -p 8000:8000 library-ai-insights-backend:latest
```

### Database/CSV Files

The backend loads data at startup from:
- CSV: `app/data/csv/enriched_books_filtered.csv` (~119K books)
- Recommendations: `app/services/book_recommendations.json` (lazy-loaded)

Startup may take 3-5 seconds for CSV load. Cache the API responses on the frontend.

---

## API Reference Summary

| Endpoint | Method | Purpose | Pagination |
|----------|--------|---------|-----------|
| `/books/search` | GET | Smart multi-source search | Yes |
| `/books/search/title` | GET | Title-only search | Yes |
| `/books/search/author` | GET | Author-only search | Yes |
| `/books/search/category` | GET | Category browsing | Yes |
| `/books/trending` | GET | Top-rated books | Yes |
| `/books/{isbn}` | GET | Book details | No |
| `/books/{isbn}/similar` | GET | Recommendations | No |
| `/books/stats` | GET | Statistics | No |
| `/health` | GET | Health check | No |

---

## Support & Troubleshooting

**Backend won't start?**
- Check Python version is 3.8+
- Verify CSV file exists at `app/data/csv/enriched_books_filtered.csv`
- Check port 8000 is not in use: `lsof -i :8000`

**Search returns 0 results?**
- Try searching for common words like "python", "data", "fiction"
- Backend currently does substring matching on title/author
- Category search supports typo-tolerant correction (example: `foction` → `fiction`)

**Slow backend startup?**
- CSV load (~119K books) takes 2-5 seconds
- Recommendations lazy-load on first request
- Cache API responses on frontend

---

**Last Updated:** February 23, 2026  
**Backend Version:** 1.0.0  
**API Version:** 1.0

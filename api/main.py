import sqlite3
import subprocess
import os
from pathlib import Path
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

app = FastAPI(title="XVideos Crawler API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths
DB_PATH = Path(__file__).parent.parent / "data" / "videos.db"
STATIC_DIR = Path(__file__).parent / "static"
CRAWLER_JS = Path(__file__).parent.parent / "index-fresh.js"

def init_db():
    """Ensure the SQLite database and schema exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_path TEXT UNIQUE NOT NULL,
            url TEXT NOT NULL,
            title TEXT,
            duration TEXT,
            profile_name TEXT,
            profile_url TEXT,
            views TEXT,
            page_number INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_page ON videos(page_number)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_created ON videos(created_at)")
    conn.commit()
    conn.close()

def get_db():
    init_db()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/api/videos")
def list_videos(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None)
):
    conn = get_db()
    cursor = conn.cursor()

    offset = (page - 1) * limit
    
    if search:
        search_term = f"%{search}%"
        cursor.execute(
            "SELECT COUNT(*) as total FROM videos WHERE title LIKE ?",
            (search_term,)
        )
        total = cursor.fetchone()["total"]
        cursor.execute(
            "SELECT * FROM videos WHERE title LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (search_term, limit, offset)
        )
    else:
        cursor.execute("SELECT COUNT(*) as total FROM videos")
        total = cursor.fetchone()["total"]
        cursor.execute(
            "SELECT * FROM videos ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )
    
    rows = cursor.fetchall()
    conn.close()

    videos = [dict(row) for row in rows]

    return {
        "videos": videos,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit
        }
    }


@app.get("/api/stats")
def get_stats():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total, MAX(created_at) as last_crawl FROM videos")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {"total": 0, "last_crawl": None}


@app.post("/api/crawl")
def trigger_crawl(pages: int = Query(1, ge=1, le=10)):
    if not CRAWLER_JS.exists():
        return JSONResponse({"error": "Crawler not found"}, status_code=500)

    try:
        result = subprocess.run(
            ["node", str(CRAWLER_JS), str(pages)],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(CRAWLER_JS.parent)
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# Static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def read_root():
    return FileResponse(str(STATIC_DIR / "index.html"))

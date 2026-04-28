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
DETAILS_DB_PATH = Path(__file__).parent.parent / "data" / "video_details.db"
STATIC_DIR = Path(__file__).parent / "static"
CRAWLER_JS = Path(__file__).parent.parent / "index-fresh.js"
CRAWLER_BEST_JS = Path(__file__).parent.parent / "crawler-best.js"
SAVE_DETAILS_JS = Path(__file__).parent.parent / "data" / "save_details.js"


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


def get_details_db():
    DETAILS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DETAILS_DB_PATH))
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

    details_conn = get_details_db()
    details_cursor = details_conn.cursor()
    details_cursor.execute("SELECT COUNT(*) as total_details FROM video_details")
    details_row = details_cursor.fetchone()
    details_conn.close()

    result = dict(row) if row else {"total": 0, "last_crawl": None}
    result["total_details"] = details_row["total_details"] if details_row else 0
    return result


@app.get("/api/video_details")
def list_video_details(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None)
):
    if not DETAILS_DB_PATH.exists():
        return {
            "videos": [],
            "pagination": {"page": page, "limit": limit, "total": 0, "pages": 0}
        }

    conn = get_details_db()
    cursor = conn.cursor()
    offset = (page - 1) * limit

    if search:
        search_term = f"%{search}%"
        cursor.execute(
            "SELECT COUNT(*) as total FROM video_details WHERE title LIKE ?",
            (search_term,)
        )
        total = cursor.fetchone()["total"]
        cursor.execute(
            "SELECT * FROM video_details WHERE title LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (search_term, limit, offset)
        )
    else:
        cursor.execute("SELECT COUNT(*) as total FROM video_details")
        total = cursor.fetchone()["total"]
        cursor.execute(
            "SELECT * FROM video_details ORDER BY created_at DESC LIMIT ? OFFSET ?",
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


@app.get("/api/video_details/{video_id}")
def get_video_detail(video_id: int):
    if not DETAILS_DB_PATH.exists():
        return JSONResponse({"error": "Details database not found"}, status_code=404)

    conn = get_details_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM video_details WHERE id = ?", (video_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return JSONResponse({"error": "Video detail not found"}, status_code=404)

    return dict(row)


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


@app.post("/api/crawl/best")
def trigger_crawl_best(
    year: str = Query("2018"),
    month: str = Query("02"),
    pages: int = Query(1, ge=1, le=10)
):
    if not CRAWLER_BEST_JS.exists():
        return JSONResponse({"error": "Best crawler not found"}, status_code=500)

    try:
        cmd = ["node", str(CRAWLER_BEST_JS), year, month, str(pages)]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(CRAWLER_BEST_JS.parent)
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "command": " ".join(cmd)
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/video_details/fetch")
def trigger_fetch_details():
    if not SAVE_DETAILS_JS.exists():
        return JSONResponse({"error": "save_details.js not found"}, status_code=500)

    try:
        result = subprocess.run(
            ["node", str(SAVE_DETAILS_JS)],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(SAVE_DETAILS_JS.parent)
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

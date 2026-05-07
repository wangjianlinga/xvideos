import sqlite3
import subprocess
import os
import re
import urllib.parse
from pathlib import Path
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from pydantic import BaseModel

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
BASE_DIR = Path(__file__).parent.parent
VIDEOS_DB = BASE_DIR / "data" / "videos.db"
CRAWLER_JS = BASE_DIR / "index-fresh.js"
CRAWLER_BEST_JS = BASE_DIR / "crawler-best.js"


class BatchDeleteRequest(BaseModel):
    ids: List[int]


def get_conn(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def parse_views_to_number(views_str: Optional[str]) -> float:
    """Parse views text like 'Author - 428.8k Views -' or '9.5M' into a float number."""
    if not views_str:
        return 0.0
    # Try 'X Views' format first
    match = re.search(r'([\d.]+)\s*([kKMm]?)\s*Views', views_str)
    if not match:
        # Fallback: any number with optional k/M suffix
        match = re.search(r'([\d.]+)\s*([kKMm]?)', views_str)
    if not match:
        return 0.0
    num = float(match.group(1))
    suffix = match.group(2).lower()
    if suffix == 'k':
        num *= 1_000
    elif suffix == 'm':
        num *= 1_000_000
    return num


def init_db():
    """Ensure the SQLite database and schema exist."""
    VIDEOS_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(VIDEOS_DB))
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
            favorite INTEGER DEFAULT 0,
            is_deleted INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_page ON videos(page_number)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_created ON videos(created_at)")
    # Migrate: add missing columns if they don't exist
    cursor.execute("PRAGMA table_info(videos)")
    columns = [row[1] for row in cursor.fetchall()]
    if "favorite" not in columns:
        cursor.execute("ALTER TABLE videos ADD COLUMN favorite INTEGER DEFAULT 0")
    if "is_deleted" not in columns:
        cursor.execute("ALTER TABLE videos ADD COLUMN is_deleted INTEGER DEFAULT 0")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_favorite ON videos(favorite)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_deleted ON videos(is_deleted)")
    conn.commit()
    conn.close()


init_db()


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/videos")
def list_videos(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    profile: Optional[str] = Query(None),
    sort: Optional[str] = Query("views_desc")
):
    conn = get_conn(VIDEOS_DB)
    cursor = conn.cursor()

    base_where = "is_deleted = 0"
    conditions = []
    params = []
    if search:
        search_term = f"%{search}%"
        conditions.append("(title LIKE ? OR profile_name LIKE ?)")
        params.extend([search_term, search_term])
    if profile:
        profile_term = f"%{profile}%"
        conditions.append("profile_name LIKE ?")
        params.append(profile_term)
    where_clause = base_where
    if conditions:
        where_clause += " AND " + " AND ".join(conditions)
    cursor.execute(f"SELECT COUNT(*) as total FROM videos WHERE {where_clause}", tuple(params))
    total = cursor.fetchone()["total"]
    cursor.execute(f"SELECT * FROM videos WHERE {where_clause}", tuple(params))

    rows = cursor.fetchall()
    conn.close()

    videos: List[dict] = [dict(row) for row in rows]

    # Sorting
    if sort == "views_desc":
        videos.sort(key=lambda v: parse_views_to_number(v.get("views")), reverse=True)
    elif sort == "views_asc":
        videos.sort(key=lambda v: parse_views_to_number(v.get("views")))
    elif sort == "title_asc":
        videos.sort(key=lambda v: (v.get("title") or "").lower())
    else:
        # default created_at_desc
        videos.sort(key=lambda v: v.get("created_at") or "", reverse=True)

    # Pagination after sorting
    offset = (page - 1) * limit
    paginated = videos[offset:offset + limit]

    return {
        "videos": paginated,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit
        }
    }


@app.get("/api/videos/{video_id}")
def get_video(video_id: int):
    conn = get_conn(VIDEOS_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return dict(row)


@app.post("/api/videos/{video_id}/favorite")
def toggle_favorite(video_id: int):
    conn = get_conn(VIDEOS_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT favorite FROM videos WHERE id = ?", (video_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return JSONResponse({"error": "Not found"}, status_code=404)
    new_favorite = 1 if row["favorite"] == 0 else 0
    cursor.execute("UPDATE videos SET favorite = ? WHERE id = ?", (new_favorite, video_id))
    conn.commit()
    conn.close()
    return {"id": video_id, "favorite": new_favorite}


@app.get("/api/videos/favorites/list")
def list_favorites(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    profile: Optional[str] = Query(None),
    sort: Optional[str] = Query("views_desc")
):
    conn = get_conn(VIDEOS_DB)
    cursor = conn.cursor()

    base_where = "favorite = 1 AND is_deleted = 0"
    conditions = []
    params = []
    if search:
        search_term = f"%{search}%"
        conditions.append("(title LIKE ? OR profile_name LIKE ?)")
        params.extend([search_term, search_term])
    if profile:
        profile_term = f"%{profile}%"
        conditions.append("profile_name LIKE ?")
        params.append(profile_term)
    where_clause = base_where
    if conditions:
        where_clause += " AND " + " AND ".join(conditions)
    cursor.execute(f"SELECT COUNT(*) as total FROM videos WHERE {where_clause}", tuple(params))
    total = cursor.fetchone()["total"]
    cursor.execute(f"SELECT * FROM videos WHERE {where_clause}", tuple(params))

    rows = cursor.fetchall()
    conn.close()

    videos: List[dict] = [dict(row) for row in rows]

    if sort == "views_desc":
        videos.sort(key=lambda v: parse_views_to_number(v.get("views")), reverse=True)
    elif sort == "views_asc":
        videos.sort(key=lambda v: parse_views_to_number(v.get("views")))
    elif sort == "title_asc":
        videos.sort(key=lambda v: (v.get("title") or "").lower())
    else:
        videos.sort(key=lambda v: v.get("created_at") or "", reverse=True)

    offset = (page - 1) * limit
    paginated = videos[offset:offset + limit]

    return {
        "videos": paginated,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit
        }
    }


@app.post("/api/videos/batch-delete")
def batch_delete(payload: BatchDeleteRequest):
    if not payload.ids:
        return JSONResponse({"error": "No ids provided"}, status_code=400)
    conn = get_conn(VIDEOS_DB)
    cursor = conn.cursor()
    placeholders = ",".join(["?"] * len(payload.ids))
    cursor.execute(f"UPDATE videos SET is_deleted = 1 WHERE id IN ({placeholders})", tuple(payload.ids))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return {"deleted": deleted}


@app.post("/api/videos/batch-restore")
def batch_restore(payload: BatchDeleteRequest):
    if not payload.ids:
        return JSONResponse({"error": "No ids provided"}, status_code=400)
    conn = get_conn(VIDEOS_DB)
    cursor = conn.cursor()
    placeholders = ",".join(["?"] * len(payload.ids))
    cursor.execute(f"UPDATE videos SET is_deleted = 0 WHERE id IN ({placeholders})", tuple(payload.ids))
    restored = cursor.rowcount
    conn.commit()
    conn.close()
    return {"restored": restored}


@app.post("/api/videos/{video_id}/restore")
def restore_video(video_id: int):
    conn = get_conn(VIDEOS_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT is_deleted FROM videos WHERE id = ?", (video_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return JSONResponse({"error": "Not found"}, status_code=404)
    cursor.execute("UPDATE videos SET is_deleted = 0 WHERE id = ?", (video_id,))
    conn.commit()
    conn.close()
    return {"id": video_id, "restored": True}


@app.get("/api/videos/deleted/list")
def list_deleted(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    profile: Optional[str] = Query(None),
    sort: Optional[str] = Query("created_at_desc")
):
    conn = get_conn(VIDEOS_DB)
    cursor = conn.cursor()

    base_where = "is_deleted = 1"
    conditions = []
    params = []
    if search:
        search_term = f"%{search}%"
        conditions.append("(title LIKE ? OR profile_name LIKE ?)")
        params.extend([search_term, search_term])
    if profile:
        profile_term = f"%{profile}%"
        conditions.append("profile_name LIKE ?")
        params.append(profile_term)
    where_clause = base_where
    if conditions:
        where_clause += " AND " + " AND ".join(conditions)
    cursor.execute(f"SELECT COUNT(*) as total FROM videos WHERE {where_clause}", tuple(params))
    total = cursor.fetchone()["total"]
    cursor.execute(f"SELECT * FROM videos WHERE {where_clause}", tuple(params))

    rows = cursor.fetchall()
    conn.close()

    videos: List[dict] = [dict(row) for row in rows]

    if sort == "views_desc":
        videos.sort(key=lambda v: parse_views_to_number(v.get("views")), reverse=True)
    elif sort == "views_asc":
        videos.sort(key=lambda v: parse_views_to_number(v.get("views")))
    elif sort == "title_asc":
        videos.sort(key=lambda v: (v.get("title") or "").lower())
    else:
        videos.sort(key=lambda v: v.get("created_at") or "", reverse=True)

    offset = (page - 1) * limit
    paginated = videos[offset:offset + limit]

    return {
        "videos": paginated,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit
        }
    }


@app.get("/api/search")
def search_videos(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    sort: Optional[str] = Query("views_desc")
):
    conn = get_conn(VIDEOS_DB)
    cursor = conn.cursor()
    search_term = f"%{q}%"
    cursor.execute(
        "SELECT COUNT(*) as total FROM videos WHERE is_deleted = 0 AND (title LIKE ? OR url LIKE ? OR profile_name LIKE ?)",
        (search_term, search_term, search_term)
    )
    total = cursor.fetchone()["total"]
    cursor.execute(
        "SELECT * FROM videos WHERE is_deleted = 0 AND (title LIKE ? OR url LIKE ? OR profile_name LIKE ?)",
        (search_term, search_term, search_term)
    )
    rows = cursor.fetchall()
    conn.close()

    videos: List[dict] = [dict(row) for row in rows]

    if sort == "views_desc":
        videos.sort(key=lambda v: parse_views_to_number(v.get("views")), reverse=True)
    elif sort == "views_asc":
        videos.sort(key=lambda v: parse_views_to_number(v.get("views")))
    elif sort == "title_asc":
        videos.sort(key=lambda v: (v.get("title") or "").lower())
    else:
        videos.sort(key=lambda v: v.get("created_at") or "", reverse=True)

    offset = (page - 1) * limit
    paginated = videos[offset:offset + limit]

    return {
        "videos": paginated,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit
        }
    }


@app.get("/api/dashboard")
def get_dashboard():
    conn = get_conn(VIDEOS_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total, MAX(created_at) as last_crawl FROM videos WHERE is_deleted = 0")
    videos_stats = dict(cursor.fetchone())
    cursor.execute("SELECT COUNT(*) as total FROM videos WHERE favorite = 1 AND is_deleted = 0")
    favorites_stats = dict(cursor.fetchone())
    cursor.execute("SELECT COUNT(*) as total FROM videos WHERE is_deleted = 1")
    deleted_stats = dict(cursor.fetchone())
    conn.close()

    return {
        "videos": videos_stats,
        "favorites": favorites_stats,
        "deleted": deleted_stats,
    }


@app.get("/api/stats")
def get_stats():
    conn = get_conn(VIDEOS_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total, MAX(created_at) as last_crawl FROM videos WHERE is_deleted = 0")
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


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>XVideos Crawler Dashboard</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body { background:#0f172a; color:#e2e8f0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto; }
  .card { background:#1e293b; border:1px solid #334155; border-radius:0.75rem; padding:1.25rem; }
  .table-wrap { overflow-x:auto; }
  table { width:100%; border-collapse:collapse; font-size:0.875rem; }
  th, td { padding:0.65rem 0.75rem; border-bottom:1px solid #334155; text-align:left; vertical-align:top; word-break:break-word; overflow-wrap:anywhere; }
  th { color:#94a3b8; font-weight:600; text-transform:uppercase; font-size:0.7rem; letter-spacing:0.05em; }
  td:nth-child(2), th:nth-child(2), td:nth-child(3), th:nth-child(3), td:nth-child(5), th:nth-child(5), td:nth-child(8), th:nth-child(8) { white-space: nowrap; }
  td:nth-child(4), th:nth-child(4) { min-width: 240px; }
  tr:hover td { background:#162032; }
  .btn { display:inline-flex; align-items:center; gap:0.35rem; padding:0.4rem 0.7rem; border-radius:0.45rem; font-size:0.8rem; font-weight:600; cursor:pointer; border:none; }
  .btn-primary { background:#3b82f6; color:#fff; }
  .btn-primary:hover { background:#2563eb; }
  .btn-ghost { background:#334155; color:#e2e8f0; }
  .btn-ghost:hover { background:#475569; }
  .btn-danger { background:#450a0a; color:#fca5a5; }
  .btn-danger:hover { background:#7f1d1d; color:#fff; }
  .badge { display:inline-block; padding:0.15rem 0.45rem; border-radius:9999px; font-size:0.7rem; font-weight:600; }
  .badge-green { background:#064e3b; color:#6ee7b7; }
  .badge-blue { background:#1e3a8a; color:#93c5fd; }
  .badge-red { background:#450a0a; color:#fca5a5; }
  .tag { font-size:0.7rem; padding:0.15rem 0.4rem; border-radius:0.3rem; background:#0f172a; border:1px solid #334155; color:#94a3b8; }
  input { background:#0f172a; border:1px solid #334155; color:#e2e8f0; padding:0.45rem 0.7rem; border-radius:0.45rem; outline:none; }
  input:focus { border-color:#3b82f6; }
  .modal-overlay { position:fixed; inset:0; background:rgba(0,0,0,0.7); display:none; align-items:center; justify-content:center; z-index:50; padding:1rem; }
  .modal-overlay.active { display:flex; }
  .modal { background:#1e293b; border:1px solid #334155; border-radius:0.75rem; max-width:900px; width:100%; max-height:90vh; overflow-y:auto; padding:1.5rem; }
  .grid-4 { display:grid; grid-template-columns:repeat(1,1fr); gap:1rem; }
  @media(min-width:640px){ .grid-4{grid-template-columns:repeat(2,1fr);} }
  @media(min-width:1024px){ .grid-4{grid-template-columns:repeat(4,1fr);} }
  .grid-2 { display:grid; grid-template-columns:1fr; gap:1rem; }
  @media(min-width:1024px){ .grid-2{grid-template-columns:repeat(2,1fr);} }
  .tab-btn.active { border-bottom:2px solid #3b82f6; color:#60a5fa; }
  .tab-btn { padding:0.5rem 0; margin-right:1.25rem; color:#94a3b8; cursor:pointer; border-bottom:2px solid transparent; }
  .thumb { width:120px; height:68px; object-fit:cover; border-radius:0.4rem; background:#0f172a; }
  .link { color:#60a5fa; text-decoration:none; }
  .link:hover { text-decoration:underline; }
  .empty { text-align:center; padding:3rem; color:#64748b; }
  .progress-bar { height:6px; background:#334155; border-radius:3px; overflow:hidden; }
  .progress-fill { height:100%; background:#3b82f6; border-radius:3px; transition:width .3s; }
  .star { cursor:pointer; font-size:1.1rem; user-select:none; }
  .star.on { color:#fbbf24; }
  .star.off { color:#64748b; }
  .batch-bar { display:none; align-items:center; gap:0.5rem; padding:0.5rem 0.75rem; background:#1e293b; border:1px solid #334155; border-radius:0.45rem; margin-bottom:0.75rem; }
  .batch-bar.active { display:inline-flex; }
  html { scrollbar-width: none; }
  body { -ms-overflow-style: none; }
  ::-webkit-scrollbar { display: none; }
</style>
</head>
<body>
<div class="max-w-7xl mx-auto px-4 py-6">
  <header class="flex items-center justify-between mb-6">
    <div>
      <h1 class="text-2xl font-bold">Crawler Dashboard</h1>
      <p class="text-sm text-slate-400 mt-1">Videos DB explorer</p>
    </div>
    <div class="flex items-center gap-2">
      <button class="btn btn-primary" onclick="triggerCrawl()">Crawl Fresh</button>
    </div>
  </header>

  <!-- Stats -->
  <div id="stats" class="grid-4 mb-6"></div>

  <!-- Tabs -->
  <div class="flex border-b border-slate-700 mb-4">
    <div class="tab-btn active" onclick="switchTab('videos')" id="tab-videos">Videos</div>
    <div class="tab-btn" onclick="switchTab('favorites')" id="tab-favorites">Favorites</div>
    <div class="tab-btn" onclick="switchTab('deleted')" id="tab-deleted">Trash</div>
  </div>

  <!-- Toolbar -->
  <div class="flex items-center gap-3 mb-4 flex-wrap">
    <input type="text" id="search" placeholder="Search title..." onkeydown="if(event.key==='Enter') doSearch()" style="min-width:200px;">
    <input type="text" id="searchProfile" placeholder="Search profile..." onkeydown="if(event.key==='Enter') doSearch()" style="min-width:160px;">
    <button class="btn btn-ghost" onclick="doSearch()">Search</button>
    <select id="sort" onchange="doSearch()" class="btn btn-ghost" style="background:#0f172a; border:1px solid #334155; color:#e2e8f0; padding:0.45rem 0.7rem; border-radius:0.45rem; outline:none; cursor:pointer;">
      <option value="views_desc" selected>Sort: Views High &rarr; Low</option>
      <option value="views_asc">Sort: Views Low &rarr; High</option>
      <option value="title_asc">Sort: Title A&rarr;Z</option>
      <option value="created_at_desc">Sort: Newest</option>
    </select>
    <div id="batchBar" class="batch-bar">
      <span class="text-xs text-slate-400" id="batchCount">0 selected</span>
      <button class="btn btn-primary" id="restoreBtn" onclick="confirmBatchRestore()" style="display:none;">Restore Selected</button>
      <button class="btn btn-danger" id="batchBtn" onclick="confirmBatchDelete()">Delete Selected</button>
    </div>
    <div class="ml-auto text-xs text-slate-400" id="pageInfo"></div>
  </div>

  <!-- Content -->
  <div id="content"></div>
  <div id="pagination" class="flex items-center justify-center gap-2 mt-6"></div>
</div>

<!-- Confirm Modal -->
<div class="modal-overlay" id="confirmModal" onclick="if(event.target===this)closeConfirmModal()">
  <div class="modal" style="max-width:400px;">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-bold">Confirm Delete</h2>
      <button class="btn btn-ghost" onclick="closeConfirmModal()">Cancel</button>
    </div>
    <p class="text-sm text-slate-400 mb-4">Are you sure you want to move the selected videos to Trash? They can be restored later.</p>
    <div class="flex justify-end gap-2">
      <button class="btn btn-ghost" onclick="closeConfirmModal()">Cancel</button>
      <button class="btn btn-danger" onclick="executeBatchDelete()">Delete</button>
    </div>
  </div>
</div>

<script>
let currentTab = 'videos';
let currentPage = 1;
let currentLimit = 20;
let selectedIds = new Set();

async function api(path, opts){
  const res = await fetch(path, opts);
  if(!res.ok){
    const err = await res.json().catch(()=>({error:'Request failed'}));
    throw new Error(err.error || 'Request failed');
  }
  return res.json();
}

function fmt(n){ return n==null?'-':n; }
function timeAgo(d){ if(!d)return '-'; const s=Math.floor((Date.now()-new Date(d))/1000); if(s<60)return s+'s ago'; if(s<3600)return Math.floor(s/60)+'m ago'; if(s<86400)return Math.floor(s/3600)+'h ago'; return Math.floor(s/86400)+'d ago'; }

async function loadDashboard(){
  const data = await api('/api/dashboard');
  const v = data.videos, f = data.favorites, d = data.deleted;
  document.getElementById('stats').innerHTML = `
    <div class="card">
      <div class="text-xs text-slate-400 uppercase tracking-wider">Videos (DB)</div>
      <div class="text-3xl font-bold mt-1">${fmt(v.total)}</div>
      <div class="text-xs text-slate-500 mt-1">Last: ${timeAgo(v.last_crawl)}</div>
    </div>
    <div class="card">
      <div class="text-xs text-slate-400 uppercase tracking-wider">Favorites</div>
      <div class="text-3xl font-bold mt-1">${fmt(f.total)}</div>
      <div class="text-xs text-slate-500 mt-1">Saved favorites</div>
    </div>
    <div class="card">
      <div class="text-xs text-slate-400 uppercase tracking-wider">Trash</div>
      <div class="text-3xl font-bold mt-1">${fmt(d.total)}</div>
      <div class="text-xs text-slate-500 mt-1">Soft-deleted videos</div>
    </div>
  `;
}

function switchTab(tab){
  currentTab = tab;
  currentPage = 1;
  selectedIds.clear();
  updateBatchBar();
  document.querySelectorAll('.tab-btn').forEach(el=>el.classList.remove('active'));
  document.getElementById('tab-'+tab).classList.add('active');
  const btn = document.getElementById('batchBtn');
  const restoreBtn = document.getElementById('restoreBtn');
  if(btn) btn.style.display = tab==='deleted' ? 'none' : 'inline-flex';
  if(restoreBtn) restoreBtn.style.display = tab==='deleted' ? 'inline-flex' : 'none';
  render();
}

async function render(){
  const search = document.getElementById('search').value.trim();
  const profile = document.getElementById('searchProfile').value.trim();
  if(currentTab==='favorites') await renderFavorites(search, profile);
  else if(currentTab==='deleted') await renderDeleted(search, profile);
  else await renderVideos(search, profile);
}

function updateBatchBar(){
  const bar = document.getElementById('batchBar');
  const count = document.getElementById('batchCount');
  if(selectedIds.size > 0){
    bar.classList.add('active');
    count.textContent = selectedIds.size + ' selected';
  } else {
    bar.classList.remove('active');
  }
}

function toggleSelect(id, checked){
  if(checked) selectedIds.add(id);
  else selectedIds.delete(id);
  updateBatchBar();
}

function toggleSelectAll(checked, ids){
  if(checked) ids.forEach(id=>selectedIds.add(id));
  else ids.forEach(id=>selectedIds.delete(id));
  updateBatchBar();
}

async function toggleFavorite(id, el){
  try {
    const data = await api('/api/videos/'+id+'/favorite', {method:'POST'});
    el.textContent = data.favorite ? '\u2605' : '\u2606';
    el.className = 'star ' + (data.favorite ? 'on' : 'off');
    loadDashboard();
  } catch(e) {
    alert('Failed to toggle favorite: '+e.message);
  }
}

function confirmBatchDelete(){
  if(selectedIds.size===0) return;
  document.getElementById('confirmModal').classList.add('active');
}

function confirmBatchRestore(){
  if(selectedIds.size===0) return;
  executeBatchRestore();
}

function closeConfirmModal(){
  document.getElementById('confirmModal').classList.remove('active');
}

async function executeBatchDelete(){
  closeConfirmModal();
  if(selectedIds.size===0) return;
  try {
    const data = await api('/api/videos/batch-delete', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ids: Array.from(selectedIds)})
    });
    selectedIds.clear();
    updateBatchBar();
    loadDashboard();
    render();
    alert('Moved '+data.deleted+' video(s) to Trash');
  } catch(e) {
    alert('Delete failed: '+e.message);
  }
}

async function executeBatchRestore(){
  if(selectedIds.size===0) return;
  try {
    const data = await api('/api/videos/batch-restore', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ids: Array.from(selectedIds)})
    });
    selectedIds.clear();
    updateBatchBar();
    loadDashboard();
    render();
    alert('Restored '+data.restored+' video(s)');
  } catch(e) {
    alert('Restore failed: '+e.message);
  }
}

async function renderVideos(search, profile){
  const sort = document.getElementById('sort').value;
  const q = search ? `&search=${encodeURIComponent(search)}` : '';
  const qp = profile ? `&profile=${encodeURIComponent(profile)}` : '';
  const data = await api(`/api/videos?page=${currentPage}&limit=${currentLimit}&sort=${encodeURIComponent(sort)}${q}${qp}`);
  const v = data.videos, p = data.pagination;
  const pageIds = v.map(r=>r.id);
  let html = '<div class="table-wrap"><table><thead><tr><th><input type="checkbox" id="selectAll" onclick="toggleSelectAll(this.checked, ['+pageIds.join(',')+'])"></th><th>ID</th><th>Fav</th><th>Title</th><th>Duration</th><th>Profile</th><th>Views</th><th>Crawled</th></tr></thead><tbody>';
  if(!v.length){ html += '<tr><td colspan="8" class="empty">No videos found</td></tr>'; }
  else for(const row of v){
    const profileLink = row.profile_url && row.profile_url.startsWith('http')
      ? `<a class="link" href="${row.profile_url}" target="_blank">${row.profile_url.substring(0,50)}${row.profile_url.length>50?'...':''}</a>`
      : '<span class="text-xs text-slate-500">-</span>';
    const isFav = row.favorite ? 'on' : 'off';
    const star = row.favorite ? '\u2605' : '\u2606';
    const checked = selectedIds.has(row.id) ? 'checked' : '';
    html += `<tr>
      <td><input type="checkbox" ${checked} onchange="toggleSelect(${row.id}, this.checked)"></td>
      <td>${row.id}</td>
      <td><span class="star ${isFav}" onclick="toggleFavorite(${row.id}, this)">${star}</span></td>
      <td><div class="font-semibold">${fmt(row.title)}</div><a class="link" href="${row.url}" target="_blank">${row.url.substring(0,60)}${row.url.length>60?'...':''}</a></td>
      <td>${fmt(row.duration)}</td>
      <td>${profileLink}</td>
      <td>${fmt(row.views)}</td>
      <td class="text-xs text-slate-400">${timeAgo(row.created_at)}</td>
    </tr>`;
  }
  html += '</tbody></table></div>';
  document.getElementById('content').innerHTML = html;
  document.getElementById('pageInfo').textContent = `Page ${p.page} of ${p.pages} (${p.total} total)`;
  renderPagination(p.page, p.pages);
}


async function renderDeleted(search, profile){
  const sort = document.getElementById('sort').value;
  const q = search ? `&search=${encodeURIComponent(search)}` : '';
  const qp = profile ? `&profile=${encodeURIComponent(profile)}` : '';
  const data = await api(`/api/videos/deleted/list?page=${currentPage}&limit=${currentLimit}&sort=${encodeURIComponent(sort)}${q}${qp}`);
  const v = data.videos, p = data.pagination;
  const pageIds = v.map(r=>r.id);
  let html = '<div class="table-wrap"><table><thead><tr><th><input type="checkbox" id="selectAll" onclick="toggleSelectAll(this.checked, ['+pageIds.join(',')+'])"></th><th>ID</th><th>Fav</th><th>Title</th><th>Duration</th><th>Profile</th><th>Views</th><th>Crawled</th><th>Action</th></tr></thead><tbody>';
  if(!v.length){ html += '<tr><td colspan="9" class="empty">No deleted videos</td></tr>'; }
  else for(const row of v){
    const profileLink = row.profile_url && row.profile_url.startsWith('http')
      ? `<a class="link" href="${row.profile_url}" target="_blank">${row.profile_url.substring(0,50)}${row.profile_url.length>50?'...':''}</a>`
      : '<span class="text-xs text-slate-500">-</span>';
    const isFav = row.favorite ? 'on' : 'off';
    const star = row.favorite ? '\u2605' : '\u2606';
    const checked = selectedIds.has(row.id) ? 'checked' : '';
    html += `<tr>
      <td><input type="checkbox" ${checked} onchange="toggleSelect(${row.id}, this.checked)"></td>
      <td>${row.id}</td>
      <td><span class="star ${isFav}" onclick="toggleFavorite(${row.id}, this)">${star}</span></td>
      <td><div class="font-semibold">${fmt(row.title)}</div><a class="link" href="${row.url}" target="_blank">${row.url.substring(0,60)}${row.url.length>60?'...':''}</a></td>
      <td>${fmt(row.duration)}</td>
      <td>${profileLink}</td>
      <td>${fmt(row.views)}</td>
      <td class="text-xs text-slate-400">${timeAgo(row.created_at)}</td>
      <td><button class="btn btn-primary" onclick="restoreVideo(${row.id})">Restore</button></td>
    </tr>`;
  }
  html += '</tbody></table></div>';
  document.getElementById('content').innerHTML = html;
  document.getElementById('pageInfo').textContent = `Page ${p.page} of ${p.pages} (${p.total} total)`;
  renderPagination(p.page, p.pages);
}

async function restoreVideo(id){
  try {
    await api('/api/videos/'+id+'/restore', {method:'POST'});
    loadDashboard();
    render();
  } catch(e) {
    alert('Failed to restore: '+e.message);
  }
}

async function renderFavorites(search, profile){
  const sort = document.getElementById('sort').value;
  const q = search ? `&search=${encodeURIComponent(search)}` : '';
  const qp = profile ? `&profile=${encodeURIComponent(profile)}` : '';
  const data = await api(`/api/videos/favorites/list?page=${currentPage}&limit=${currentLimit}&sort=${encodeURIComponent(sort)}${q}${qp}`);
  const v = data.videos, p = data.pagination;
  const pageIds = v.map(r=>r.id);
  let html = '<div class="table-wrap"><table><thead><tr><th><input type="checkbox" id="selectAll" onclick="toggleSelectAll(this.checked, ['+pageIds.join(',')+'])"></th><th>ID</th><th>Fav</th><th>Title</th><th>Duration</th><th>Profile</th><th>Views</th><th>Crawled</th></tr></thead><tbody>';
  if(!v.length){ html += '<tr><td colspan="8" class="empty">No favorites found</td></tr>'; }
  else for(const row of v){
    const profileLink = row.profile_url && row.profile_url.startsWith('http')
      ? `<a class="link" href="${row.profile_url}" target="_blank">${row.profile_url.substring(0,50)}${row.profile_url.length>50?'...':''}</a>`
      : '<span class="text-xs text-slate-500">-</span>';
    const isFav = row.favorite ? 'on' : 'off';
    const star = row.favorite ? '\u2605' : '\u2606';
    const checked = selectedIds.has(row.id) ? 'checked' : '';
    html += `<tr>
      <td><input type="checkbox" ${checked} onchange="toggleSelect(${row.id}, this.checked)"></td>
      <td>${row.id}</td>
      <td><span class="star ${isFav}" onclick="toggleFavorite(${row.id}, this)">${star}</span></td>
      <td><div class="font-semibold">${fmt(row.title)}</div><a class="link" href="${row.url}" target="_blank">${row.url.substring(0,60)}${row.url.length>60?'...':''}</a></td>
      <td>${fmt(row.duration)}</td>
      <td>${profileLink}</td>
      <td>${fmt(row.views)}</td>
      <td class="text-xs text-slate-400">${timeAgo(row.created_at)}</td>
    </tr>`;
  }
  html += '</tbody></table></div>';
  document.getElementById('content').innerHTML = html;
  document.getElementById('pageInfo').textContent = `Page ${p.page} of ${p.pages} (${p.total} total)`;
  renderPagination(p.page, p.pages);
}

function renderPagination(page, pages){
  let html = '';
  if(page>1) html += `<button class="btn btn-ghost" onclick="goPage(${page-1})">Prev</button>`;
  html += `<span class="text-sm text-slate-400">Page ${page} / ${pages}</span>`;
  if(page<pages) html += `<button class="btn btn-ghost" onclick="goPage(${page+1})">Next</button>`;
  document.getElementById('pagination').innerHTML = html;
}

function goPage(n){ currentPage=n; render(); }
function doSearch(){ currentPage=1; render(); }

async function triggerCrawl(){
  const pages = prompt('Pages to crawl?', '1');
  if(!pages) return;
  const btn = document.querySelector('header button:last-child');
  const orig = btn.textContent;
  btn.textContent = 'Crawling...';
  btn.disabled = true;
  const res = await fetch('/api/crawl?pages='+encodeURIComponent(pages), {method:'POST'});
  const data = await res.json();
  btn.textContent = orig;
  btn.disabled = false;
  alert(data.success ? 'Crawl finished. Check console.' : 'Crawl failed: '+(data.error||data.stderr||'Unknown'));
  loadDashboard();
  render();
}

loadDashboard();
render();
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return DASHBOARD_HTML

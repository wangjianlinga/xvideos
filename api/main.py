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
DETAIL_DB = BASE_DIR / "data" / "videos-detail.db"
CRAWLER_JS = BASE_DIR / "index-fresh.js"
CRAWLER_BEST_JS = BASE_DIR / "crawler-best.js"


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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_page ON videos(page_number)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_created ON videos(created_at)")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/videos")
def list_videos(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    sort: Optional[str] = Query("views_desc")
):
    conn = get_conn(VIDEOS_DB)
    cursor = conn.cursor()

    if search:
        search_term = f"%{search}%"
        cursor.execute(
            "SELECT COUNT(*) as total FROM videos WHERE title LIKE ?",
            (search_term,)
        )
        total = cursor.fetchone()["total"]
        cursor.execute(
            "SELECT * FROM videos WHERE title LIKE ?",
            (search_term,)
        )
    else:
        cursor.execute("SELECT COUNT(*) as total FROM videos")
        total = cursor.fetchone()["total"]
        cursor.execute("SELECT * FROM videos")

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


@app.get("/api/details")
def list_details(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None)
):
    conn = get_conn(DETAIL_DB)
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

    details = []
    for row in rows:
        d = dict(row)
        d["files"] = {
            "low": d.pop("files_low", None),
            "high": d.pop("files_high", None),
            "HLS": d.pop("files_HLS", None),
            "thumb": d.pop("files_thumb", None),
            "thumb69": d.pop("files_thumb69", None),
            "thumbSlide": d.pop("files_thumbSlide", None),
            "thumbSlideBig": d.pop("files_thumbSlideBig", None),
        }
        details.append(d)

    return {
        "details": details,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit
        }
    }


@app.get("/api/details/by-url")
def get_detail_by_url(url: str):
    conn = get_conn(DETAIL_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM video_details WHERE url = ?", (url,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return JSONResponse({"error": "Not found"}, status_code=404)
    d = dict(row)
    d["files"] = {
        "low": d.pop("files_low", None),
        "high": d.pop("files_high", None),
        "HLS": d.pop("files_HLS", None),
        "thumb": d.pop("files_thumb", None),
        "thumb69": d.pop("files_thumb69", None),
        "thumbSlide": d.pop("files_thumbSlide", None),
        "thumbSlideBig": d.pop("files_thumbSlideBig", None),
    }
    return d


@app.get("/api/dashboard")
def get_dashboard():
    conn1 = get_conn(VIDEOS_DB)
    conn2 = get_conn(DETAIL_DB)

    c1 = conn1.cursor()
    c2 = conn2.cursor()

    c1.execute("SELECT COUNT(*) as total, MAX(created_at) as last_crawl FROM videos")
    videos_stats = dict(c1.fetchone())

    c2.execute("SELECT COUNT(*) as total, MAX(updated_at) as last_update FROM video_details")
    details_stats = dict(c2.fetchone())

    # Cross-db query via ATTACH
    c1.execute("ATTACH DATABASE ? AS detail_db", (str(DETAIL_DB),))
    c1.execute("SELECT COUNT(DISTINCT url) as matched FROM videos WHERE url IN (SELECT url FROM detail_db.video_details)")
    matched = c1.fetchone()["matched"]
    c1.execute("DETACH DATABASE detail_db")

    conn1.close()
    conn2.close()

    return {
        "videos": videos_stats,
        "details": details_stats,
        "coverage": {
            "matched": matched,
            "videos_total": videos_stats["total"],
            "details_total": details_stats["total"]
        }
    }


@app.get("/api/stats")
def get_stats():
    conn = get_conn(VIDEOS_DB)
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
  th, td { padding:0.65rem 0.75rem; border-bottom:1px solid #334155; text-align:left; vertical-align:top; }
  th { color:#94a3b8; font-weight:600; text-transform:uppercase; font-size:0.7rem; letter-spacing:0.05em; }
  tr:hover td { background:#162032; }
  .btn { display:inline-flex; align-items:center; gap:0.35rem; padding:0.4rem 0.7rem; border-radius:0.45rem; font-size:0.8rem; font-weight:600; cursor:pointer; border:none; }
  .btn-primary { background:#3b82f6; color:#fff; }
  .btn-primary:hover { background:#2563eb; }
  .btn-ghost { background:#334155; color:#e2e8f0; }
  .btn-ghost:hover { background:#475569; }
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
</style>
</head>
<body>
<div class="max-w-7xl mx-auto px-4 py-6">
  <header class="flex items-center justify-between mb-6">
    <div>
      <h1 class="text-2xl font-bold">Crawler Dashboard</h1>
      <p class="text-sm text-slate-400 mt-1">Videos DB & Detail DB explorer</p>
    </div>
    <div class="flex items-center gap-2">
      <button class="btn btn-ghost" onclick="loadDashboard()">Refresh</button>
      <button class="btn btn-primary" onclick="triggerCrawl()">Crawl Fresh</button>
    </div>
  </header>

  <!-- Stats -->
  <div id="stats" class="grid-4 mb-6"></div>

  <!-- Tabs -->
  <div class="flex border-b border-slate-700 mb-4">
    <div class="tab-btn active" onclick="switchTab('videos')" id="tab-videos">Videos</div>
    <div class="tab-btn" onclick="switchTab('details')" id="tab-details">Details</div>
  </div>

  <!-- Toolbar -->
  <div class="flex items-center gap-3 mb-4 flex-wrap">
    <input type="text" id="search" placeholder="Search title..." onkeydown="if(event.key==='Enter') doSearch()" style="min-width:240px;">
    <button class="btn btn-ghost" onclick="doSearch()">Search</button>
    <select id="sort" onchange="doSearch()" class="btn btn-ghost" style="background:#0f172a; border:1px solid #334155; color:#e2e8f0; padding:0.45rem 0.7rem; border-radius:0.45rem; outline:none; cursor:pointer;">
      <option value="views_desc" selected>Sort: Views High &rarr; Low</option>
      <option value="views_asc">Sort: Views Low &rarr; High</option>
    </select>
    <div class="ml-auto text-xs text-slate-400" id="pageInfo"></div>
  </div>

  <!-- Content -->
  <div id="content"></div>
  <div id="pagination" class="flex items-center justify-center gap-2 mt-6"></div>
</div>

<!-- Detail Modal -->
<div class="modal-overlay" id="modal" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-bold">Video Detail</h2>
      <button class="btn btn-ghost" onclick="closeModal()">Close</button>
    </div>
    <div id="modalBody"></div>
  </div>
</div>

<script>
let currentTab = 'videos';
let currentPage = 1;
let currentLimit = 20;

async function api(path){ return fetch(path).then(r=>r.json()); }

function fmt(n){ return n==null?'-':n; }
function timeAgo(d){ if(!d)return '-'; const s=Math.floor((Date.now()-new Date(d))/1000); if(s<60)return s+'s ago'; if(s<3600)return Math.floor(s/60)+'m ago'; if(s<86400)return Math.floor(s/3600)+'h ago'; return Math.floor(s/86400)+'d ago'; }

async function loadDashboard(){
  const data = await api('/api/dashboard');
  const v = data.videos, d = data.details, c = data.coverage;
  const pct = c.videos_total ? Math.round(c.matched/c.videos_total*100) : 0;
  document.getElementById('stats').innerHTML = `
    <div class="card">
      <div class="text-xs text-slate-400 uppercase tracking-wider">Videos (DB)</div>
      <div class="text-3xl font-bold mt-1">${fmt(v.total)}</div>
      <div class="text-xs text-slate-500 mt-1">Last: ${timeAgo(v.last_crawl)}</div>
    </div>
    <div class="card">
      <div class="text-xs text-slate-400 uppercase tracking-wider">Details (DB)</div>
      <div class="text-3xl font-bold mt-1">${fmt(d.total)}</div>
      <div class="text-xs text-slate-500 mt-1">Last: ${timeAgo(d.last_update)}</div>
    </div>
    <div class="card">
      <div class="text-xs text-slate-400 uppercase tracking-wider">Coverage</div>
      <div class="text-3xl font-bold mt-1">${c.matched} / ${c.videos_total}</div>
      <div class="mt-2 progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div>
      <div class="text-xs text-slate-500 mt-1">${pct}% have detail records</div>
    </div>
    <div class="card">
      <div class="text-xs text-slate-400 uppercase tracking-wider">Workers</div>
      <div class="text-3xl font-bold mt-1">${navigator.hardwareConcurrency||'?'}</div>
      <div class="text-xs text-slate-500 mt-1">Logical cores available</div>
    </div>
  `;
}

function switchTab(tab){
  currentTab = tab;
  currentPage = 1;
  document.querySelectorAll('.tab-btn').forEach(el=>el.classList.remove('active'));
  document.getElementById('tab-'+tab).classList.add('active');
  render();
}

async function render(){
  const search = document.getElementById('search').value.trim();
  if(currentTab==='videos') await renderVideos(search);
  else await renderDetails(search);
}

async function renderVideos(search){
  const sort = document.getElementById('sort').value;
  const q = search ? `&search=${encodeURIComponent(search)}` : '';
  const data = await api(`/api/videos?page=${currentPage}&limit=${currentLimit}&sort=${encodeURIComponent(sort)}${q}`);
  const v = data.videos, p = data.pagination;
  let html = '<div class="table-wrap"><table><thead><tr><th>ID</th><th>Thumb</th><th>Title</th><th>Duration</th><th>Profile</th><th>Views</th><th>Page</th><th>Crawled</th><th>Action</th></tr></thead><tbody>';
  if(!v.length){ html += '<tr><td colspan="9" class="empty">No videos found</td></tr>'; }
  else for(const row of v){
    const profileLink = row.profile_url && row.profile_url.startsWith('http')
      ? `<a class="link" href="${row.profile_url}" target="_blank">${row.profile_url.substring(0,50)}${row.profile_url.length>50?'...':''}</a>`
      : '<span class="text-xs text-slate-500">-</span>';
    html += `<tr>
      <td>${row.id}</td>
      <td><img class="thumb" src="https://img-l3.xvideos-cdn.com/videos/thumbs169ll/default.jpg" onerror="this.style.display='none'" alt=""></td>
      <td><div class="font-semibold">${fmt(row.title)}</div><a class="link" href="${row.url}" target="_blank">${row.url.substring(0,60)}${row.url.length>60?'...':''}</a></td>
      <td>${fmt(row.duration)}</td>
      <td>${profileLink}</td>
      <td>${fmt(row.views)}</td>
      <td>${fmt(row.page_number)}</td>
      <td class="text-xs text-slate-400">${timeAgo(row.created_at)}</td>
      <td><button class="btn btn-ghost" onclick="viewDetailByUrl('${encodeURIComponent(row.url)}')">Detail</button></td>
    </tr>`;
  }
  html += '</tbody></table></div>';
  document.getElementById('content').innerHTML = html;
  document.getElementById('pageInfo').textContent = `Page ${p.page} of ${p.pages} (${p.total} total)`;
  renderPagination(p.page, p.pages);
}

async function renderDetails(search){
  const q = search ? `&search=${encodeURIComponent(search)}` : '';
  const data = await api(`/api/details?page=${currentPage}&limit=${currentLimit}${q}`);
  const d = data.details, p = data.pagination;
  let html = '<div class="table-wrap"><table><thead><tr><th>ID</th><th>Title</th><th>Duration</th><th>Type</th><th>Resolution</th><th>Views</th><th>Files</th><th>Updated</th></tr></thead><tbody>';
  if(!d.length){ html += '<tr><td colspan="8" class="empty">No details found</td></tr>'; }
  else for(const row of d){
    const files = row.files||{};
    const hasFiles = Object.values(files).some(x=>x);
    html += `<tr>
      <td>${row.id}</td>
      <td><div class="font-semibold">${fmt(row.title)}</div><a class="link" href="${row.url}" target="_blank">${row.url.substring(0,50)}${row.url.length>50?'...':''}</a></td>
      <td>${fmt(row.duration)}</td>
      <td><span class="tag">${fmt(row.videoType)}</span></td>
      <td>${fmt(row.videoWidth)}×${fmt(row.videoHeight)}</td>
      <td>${fmt(row.views)}</td>
      <td>${hasFiles?'<span class=\\'badge badge-green\\'>Yes</span>':'<span class=\\'badge badge-red\\'>No</span>'}</td>
      <td class="text-xs text-slate-400">${timeAgo(row.updated_at)}</td>
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

async function viewDetailByUrl(encUrl){
  const url = decodeURIComponent(encUrl);
  const data = await api('/api/details/by-url?url='+encodeURIComponent(url));
  const files = data.files||{};
  const fileItems = Object.entries(files).filter(([,v])=>v).map(([k,v])=>`<div class="flex items-center justify-between py-1 border-b border-slate-700"><span class="text-xs text-slate-400">${k}</span><a class="link text-xs" href="${v}" target="_blank">${v.substring(0,60)}${v.length>60?'...':''}</a></div>`).join('') || '<div class="text-sm text-slate-500">No file URLs available</div>';
  document.getElementById('modalBody').innerHTML = `
    <div class="grid-2">
      <div>
        <div class="mb-3"><div class="text-xs text-slate-400">Title</div><div class="font-semibold">${fmt(data.title)}</div></div>
        <div class="mb-3"><div class="text-xs text-slate-400">URL</div><a class="link text-sm" href="${data.url}" target="_blank">${data.url}</a></div>
        <div class="mb-3"><div class="text-xs text-slate-400">Duration</div><div>${fmt(data.duration)}</div></div>
        <div class="mb-3"><div class="text-xs text-slate-400">Views</div><div>${fmt(data.views)}</div></div>
        <div class="mb-3"><div class="text-xs text-slate-400">Video Type</div><div><span class="tag">${fmt(data.videoType)}</span></div></div>
        <div class="mb-3"><div class="text-xs text-slate-400">Resolution</div><div>${fmt(data.videoWidth)} × ${fmt(data.videoHeight)}</div></div>
      </div>
      <div>
        <div class="text-xs text-slate-400 mb-2">Files</div>
        <div class="card" style="padding:0.75rem 1rem;">${fileItems}</div>
        ${data.image?`<img src="${data.image}" class="mt-3 thumb" style="width:100%;height:auto;max-height:200px;" onerror="this.style.display='none'" alt="Thumb">`:''}
      </div>
    </div>
  `;
  document.getElementById('modal').classList.add('active');
}

function closeModal(){ document.getElementById('modal').classList.remove('active'); }

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

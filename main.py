
import os, re, shutil, tempfile, subprocess, shlex, time
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from starlette.responses import StreamingResponse, JSONResponse, Response
import yt_dlp
import orjson

APP_NAME = "PKS YOU V DOWNLOADER API"
VERSION = "v1-pro"

def ojson_dumps(v, *, default):
    return orjson.dumps(v, default=default)

app = FastAPI(title=APP_NAME, version=VERSION, default_response_class=Response)
app.router.default_response_class = Response

# CORS
origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "https://pksyouv.vercel.app",
    "https://*.vercel.app",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# Simple in-memory rate limit (best effort)
RATE_LIMIT = {"window": 60, "max": 60}  # 60 req/min per IP
BUCKETS: Dict[str, List[float]] = {}

def allow_request(ip: str) -> bool:
    now = time.time()
    win = RATE_LIMIT["window"]
    bucket = BUCKETS.setdefault(ip, [])
    # drop old
    BUCKETS[ip] = [t for t in bucket if now - t < win]
    if len(BUCKETS[ip]) >= RATE_LIMIT["max"]:
        return False
    BUCKETS[ip].append(now)
    return True

def safe_filename(name: str, ext: str = "") -> str:
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name).strip()
    if not name:
        name = "video"
    if ext and not name.lower().endswith(f".{ext}"):
        name = f"{name}.{ext}"
    return name

class InfoIn(BaseModel):
    url: HttpUrl

@app.middleware("http")
async def limiter(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"
    if not allow_request(ip):
        return JSONResponse({"error": "rate_limited"}, status_code=429)
    return await call_next(request)

@app.get("/health")
def health():
    return JSONResponse({"ok": True, "app": APP_NAME, "version": VERSION})

@app.post("/api/info")
def get_info(payload: InfoIn):
    url = str(payload.url)
    ydl_opts = {
        "quiet": True,
        "nocheckcertificate": True,
        "geo_bypass": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "hi", "en-US", "en-IN", "hi-IN", "all"],
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            data = ydl.extract_info(url, download=False)
        if "entries" in data:
            data = data["entries"][0]

        # collect formats
        fmts = []
        for f in data.get("formats", []):
            if not f.get("url"):
                continue
            ext = f.get("ext")
            h = f.get("height")
            ac = f.get("acodec"); vc = f.get("vcodec")
            size = f.get("filesize") or f.get("filesize_approx")
            label = []
            if h: label.append(f"{h}p")
            if vc and vc != "none": label.append("video")
            if ac and ac != "none": label.append("audio")
            quality = "/".join(label) if label else (ext or "stream")
            fmts.append({
                "format_id": f.get("format_id"),
                "ext": ext,
                "quality": quality,
                "filesize": size,
                "url": f.get("url"),
                "height": h, "width": f.get("width"),
                "fps": f.get("fps"), "abr": f.get("abr"), "vbr": f.get("vbr"),
            })
        fmts = sorted(fmts, key=lambda x: (x["height"] or 0, x["abr"] or 0), reverse=True)

        # collect subtitles
        subs = []
        sd = data.get("subtitles") or data.get("automatic_captions") or {}
        for lang, tracks in sd.items():
            for t in tracks:
                subs.append({
                    "lang": lang,
                    "ext": t.get("ext"),
                    "url": t.get("url")
                })

        out = {
            "title": data.get("title"),
            "thumbnail": data.get("thumbnail"),
            "duration": data.get("duration"),
            "channel": data.get("uploader"),
            "webpage_url": data.get("webpage_url"),
            "formats": fmts,
            "subtitles": subs,
            "note": "Direct links expire; use soon or use server proxy endpoints.",
        }
        return JSONResponse(out)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

def stream_proc(cmd: list):
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=10**6)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start: {e}")
    def gen():
        try:
            while True:
                chunk = proc.stdout.read(1024 * 64)
                if not chunk:
                    break
                yield chunk
        finally:
            try:
                proc.stdout.close(); proc.stderr.close()
            except Exception:
                pass
            proc.terminate()
    return gen

@app.get("/api/download")
def download(url: str = Query(...), format_id: str = Query(...), filename: str = Query("video")):
    name = safe_filename(filename)
    cmd = ["yt-dlp", "-f", format_id, "-o", "-", url]
    headers = {"Content-Disposition": f"attachment; filename={name}"}
    return StreamingResponse(stream_proc(cmd)(), headers=headers, media_type="application/octet-stream")

@app.get("/api/grab_mp4")
def grab_mp4(url: str = Query(...), height: int = Query(1080), filename: str = Query("video.mp4")):
    tmpdir = tempfile.mkdtemp(prefix="pksmp4_")
    outfile = os.path.join(tmpdir, "out.mp4")
    selector = f"bv*[height<={height}]+ba/best[height<={height}]"
    cmd = ["yt-dlp", "-f", selector, "--recode-video", "mp4", "-o", outfile, url]
    try:
        subprocess.check_call(cmd)
        fpath = outfile
    except subprocess.CalledProcessError:
        fallback = os.path.join(tmpdir, "fallback.%(ext)s")
        cmd2 = ["yt-dlp", "-f", f"best[ext=mp4][height<={height}]/best", "-o", fallback, url]
        subprocess.check_call(cmd2)
        files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if os.path.isfile(os.path.join(tmpdir,f))]
        if not files:
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise HTTPException(status_code=500, detail="Download failed.")
        fpath = files[0]

    download_name = safe_filename(os.path.splitext(filename)[0], "mp4")
    def iterfile():
        with open(fpath, "rb") as f:
            while True:
                chunk = f.read(1024*64)
                if not chunk: break
                yield chunk
        shutil.rmtree(tmpdir, ignore_errors=True)

    headers = {"Content-Disposition": f"attachment; filename={download_name}"}
    return StreamingResponse(iterfile(), headers=headers, media_type="video/mp4")

@app.get("/api/grab_mp3")
def grab_mp3(url: str = Query(...), filename: str = Query("audio.mp3")):
    tmpdir = tempfile.mkdtemp(prefix="pksmp3_")
    mp3file = os.path.join(tmpdir, "audio.mp3")
    cmd = ["yt-dlp", "-f", "bestaudio/best", "--extract-audio", "--audio-format", "mp3", "--audio-quality", "192K", "-o", mp3file, url]
    try:
        subprocess.check_call(cmd)
        fpath = mp3file; media = "audio/mpeg"
    except subprocess.CalledProcessError:
        raw = os.path.join(tmpdir, "audio.%(ext)s")
        subprocess.check_call(["yt-dlp", "-f", "bestaudio/best", "-o", raw, url])
        files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir)]
        if not files:
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise HTTPException(status_code=500, detail="Audio download failed.")
        fpath = files[0]; media = "application/octet-stream"

    download_name = safe_filename(os.path.splitext(filename)[0], "mp3")
    def iterfile():
        with open(fpath, "rb") as f:
            while True:
                chunk = f.read(1024*64)
                if not chunk: break
                yield chunk
        shutil.rmtree(tmpdir, ignore_errors=True)

    headers = {"Content-Disposition": f"attachment; filename={download_name}"}
    return StreamingResponse(iterfile(), headers=headers, media_type=media)

@app.get("/api/captions")
def captions(url: str = Query(...)):
    """Return available subtitle/caption tracks (lang, ext, url)."""
    ydl_opts = {"quiet": True, "skip_download": True, "writesubtitles": True, "writeautomaticsub": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            data = ydl.extract_info(url, download=False)
        if "entries" in data: data = data["entries"][0]
        subs = []
        sd = data.get("subtitles") or data.get("automatic_captions") or {}
        for lang, tracks in sd.items():
            for t in tracks:
                subs.append({"lang": lang, "ext": t.get("ext"), "url": t.get("url")})
        return JSONResponse({"subtitles": subs})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

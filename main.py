import os
from typing import Optional, Literal
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from pydantic import BaseModel, Field
from datetime import datetime

from database import db, create_document, get_documents
from bson import ObjectId

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE = "https://api.themoviedb.org/3"
IMG_W500 = "https://image.tmdb.org/t/p/w500"
IMG_ORIGINAL = "https://image.tmdb.org/t/p/original"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------- Helpers ----------------------

def tmdb_get(path: str, params: Optional[dict] = None):
    if not TMDB_API_KEY:
        raise HTTPException(status_code=500, detail="TMDB_API_KEY is not set in environment")
    url = f"{TMDB_BASE}{path}"
    qp = {"api_key": TMDB_API_KEY, "language": "en-US"}
    if params:
        qp.update(params)
    r = requests.get(url, params=qp, timeout=12)
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


def map_item(item):
    # Works for both movie and tv results
    media_type = item.get("media_type") or ("tv" if item.get("name") else "movie")
    title = item.get("title") or item.get("name")
    date = item.get("release_date") or item.get("first_air_date")
    return {
        "id": item.get("id"),
        "media_type": media_type,
        "title": title,
        "overview": item.get("overview"),
        "poster": f"{IMG_W500}{item['poster_path']}" if item.get("poster_path") else None,
        "backdrop": f"{IMG_ORIGINAL}{item['backdrop_path']}" if item.get("backdrop_path") else None,
        "rating": item.get("vote_average"),
        "votes": item.get("vote_count"),
        "year": int(date.split("-")[0]) if date else None,
    }


# ---------------------- Models ----------------------

class WatchlistCreate(BaseModel):
    user_id: str
    tmdb_id: int
    media_type: Literal["movie", "tv"] = "movie"
    title: str
    poster: Optional[str] = None
    backdrop: Optional[str] = None
    year: Optional[int] = None
    status: Literal["later", "watching", "watched"] = "later"
    liked: bool = False
    rating: Optional[float] = Field(None, ge=0, le=10)

class WatchlistUpdate(BaseModel):
    status: Optional[Literal["later", "watching", "watched"]] = None
    liked: Optional[bool] = None
    rating: Optional[float] = Field(None, ge=0, le=10)


# ---------------------- Base Endpoints ----------------------

@app.get("/")
def read_root():
    return {"message": "Moviesque backend is running"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from Moviesque API"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
                response["connection_status"] = "Connected"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


# ---------------------- TMDb Proxy Endpoints ----------------------

@app.get("/api/trending")
def trending():
    data = tmdb_get("/trending/all/day")
    results = [map_item(x) for x in data.get("results", [])]
    return {"results": results}

@app.get("/api/top-rated")
def top_rated_movies():
    data = tmdb_get("/movie/top_rated")
    results = [map_item(x) for x in data.get("results", [])]
    return {"results": results}

@app.get("/api/popular-tv")
def popular_tv():
    data = tmdb_get("/tv/popular")
    results = [map_item(x) for x in data.get("results", [])]
    return {"results": results}

@app.get("/api/upcoming")
def upcoming_movies():
    data = tmdb_get("/movie/upcoming")
    results = [map_item(x) for x in data.get("results", [])]
    return {"results": results}

@app.get("/api/search")
def search(q: str = Query(..., min_length=1), year: Optional[int] = None):
    params = {"query": q, "include_adult": False}
    if year:
        params["year"] = year
    data = tmdb_get("/search/multi", params=params)
    # Filter only movie/tv
    filtered = [x for x in data.get("results", []) if x.get("media_type") in ("movie", "tv")]
    results = [map_item(x) for x in filtered]
    return {"results": results}

@app.get("/api/title/{media_type}/{tmdb_id}")
def title_details(media_type: Literal["movie", "tv"], tmdb_id: int):
    path = f"/{media_type}/{tmdb_id}"
    data = tmdb_get(path, params={"append_to_response": "videos,credits"})
    # Build minimal payload
    item = map_item(data)
    item["genres"] = [g.get("name") for g in data.get("genres", [])]
    item["runtime"] = data.get("runtime") or (data.get("episode_run_time", [None])[0] if data.get("episode_run_time") else None)
    item["release_date"] = data.get("release_date") or data.get("first_air_date")
    item["tagline"] = data.get("tagline")
    item["cast"] = [
        {"id": c.get("id"), "name": c.get("name"), "character": c.get("character"), "profile": f"{IMG_W500}{c['profile_path']}" if c.get("profile_path") else None}
        for c in (data.get("credits", {}).get("cast", [])[:10])
    ]
    # YouTube trailer
    videos = data.get("videos", {}).get("results", [])
    yt = next((v for v in videos if v.get("site") == "YouTube" and v.get("type") in ("Trailer", "Teaser")), None)
    item["trailer_key"] = yt.get("key") if yt else None
    return item


# ---------------------- Watchlist Endpoints ----------------------

@app.get("/api/watchlist")
def get_watchlist(user_id: str, status: Optional[str] = None):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    filt = {"user_id": user_id}
    if status:
        filt["status"] = status
    docs = db["watchlistitem"].find(filt).sort("created_at", -1)
    items = []
    for d in docs:
        d["_id"] = str(d["_id"])
        items.append(d)
    return {"results": items}

@app.post("/api/watchlist")
def add_watchlist_item(payload: WatchlistCreate):
    try:
        inserted_id = create_document("watchlistitem", payload)
        return {"id": inserted_id, "status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/watchlist/{item_id}")
def update_watchlist_item(item_id: str, payload: WatchlistUpdate):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    try:
        update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
        if not update_data:
            return {"status": "no-op"}
        update_data["updated_at"] = datetime.utcnow()
        res = db["watchlistitem"].update_one({"_id": ObjectId(item_id)}, {"$set": update_data})
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail="Item not found")
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/watchlist/{item_id}")
def delete_watchlist_item(item_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    try:
        res = db["watchlistitem"].delete_one({"_id": ObjectId(item_id)})
        if res.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Item not found")
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

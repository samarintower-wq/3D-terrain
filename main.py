import os
from datetime import datetime, timezone
from typing import Optional
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    from pymongo import MongoClient
except Exception:
    MongoClient = None

app = FastAPI(title="TerraWalk AI")
app.mount("/static", StaticFiles(directory="static"), name="static")
OW = os.getenv("OPENWEATHER_API_KEY", "")
GROQ = os.getenv("GROQ_API_KEY", "")
CF_ACCOUNT = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
CF_KEY = os.getenv("CLOUDFLARE_API_KEY", "") or os.getenv("CLOUDFLARE_API_TOKEN", "")
MONGO = os.getenv("MONGODB_URI", "")
mongo_client = None

class Point(BaseModel):
    lat: float
    lon: float
    name: Optional[str] = ""

class Ask(BaseModel):
    text: str
    lat: Optional[float] = None
    lon: Optional[float] = None

def history_collection():
    global mongo_client
    if not MONGO or MongoClient is None: return None
    try:
        if mongo_client is None: mongo_client = MongoClient(MONGO, serverSelectionTimeoutMS=2500)
        return mongo_client["terra_walk_ai"]["visits"]
    except Exception:
        return None

@app.get("/", response_class=HTMLResponse)
async def home():
    return open("index.html", encoding="utf-8").read()

@app.get("/api/health")
async def health():
    return {"status":"TerraWalk AI is running","openweather":bool(OW),"groq":bool(GROQ),
            "cloudflare":bool(CF_ACCOUNT and CF_KEY),"mongodb":bool(MONGO)}

@app.get("/api/search")
async def search(q: str):
    q=q.strip()
    try:
        a,b=[float(v) for v in q.replace(",", " ").split()[:2]]
        if -90<=a<=90 and -180<=b<=180: return {"lat":a,"lon":b,"name":f"{a:.5f}, {b:.5f}"}
    except Exception: pass
    if not OW: raise HTTPException(503,"Добавьте OPENWEATHER_API_KEY в Render для поиска по названию")
    async with httpx.AsyncClient(timeout=15) as c:
        r=await c.get("https://api.openweathermap.org/geo/1.0/direct",params={"q":q,"limit":1,"appid":OW})
    if r.status_code!=200: raise HTTPException(502,"Ошибка геокодирования OpenWeather")
    data=r.json()
    if not data: raise HTTPException(404,"Место не найдено")
    p=data[0]
    return {"lat":p["lat"],"lon":p["lon"],"name":", ".join(x for x in [p.get("name"),p.get("state"),p.get("country")] if x)}

@app.get("/api/weather")
async def weather(lat:float,lon:float,name:str=""):
    if not OW: raise HTTPException(503,"Добавьте OPENWEATHER_API_KEY в Render")
    async with httpx.AsyncClient(timeout=20) as c:
        r=await c.get("https://api.openweathermap.org/data/2.5/weather",params={"lat":lat,"lon":lon,"appid":OW,"units":"metric"})
        f=await c.get("https://api.openweathermap.org/data/2.5/forecast",params={"lat":lat,"lon":lon,"appid":OW,"units":"metric"})
    if r.status_code!=200: raise HTTPException(502,"OpenWeather не вернул погоду")
    d=r.json(); fd=f.json() if f.status_code==200 else {}
    result={"name":name or d.get("name") or f"{lat:.4f}, {lon:.4f}","lat":lat,"lon":lon,
      "temp":round(d.get("main",{}).get("temp",0)),"humidity":d.get("main",{}).get("humidity",0),
      "wind":round(d.get("wind",{}).get("speed",0),1),"description":d.get("weather",[{}])[0].get("description","—"),
      "icon":d.get("weather",[{}])[0].get("icon","01d"),
      "forecast":[{"dt":x["dt"],"temp":round(x["main"]["temp"]),"icon":x["weather"][0]["icon"]} for x in fd.get("list",[])[:8]]}
    col=history_collection()
    if col is not None:
        try: col.insert_one({"name":result["name"],"lat":lat,"lon":lon,"weather":result,"created_at":datetime.now(timezone.utc)})
        except Exception: pass
    return result

@app.post("/api/assistant")
async def assistant(body:Ask):
    if not GROQ: raise HTTPException(503,"Добавьте GROQ_API_KEY в Render")
    async with httpx.AsyncClient(timeout=30) as c:
        r=await c.post("https://api.groq.com/openai/v1/chat/completions",
          headers={"Authorization":f"Bearer {GROQ}"},
          json={"model":"llama-3.3-70b-versatile","messages":[
            {"role":"system","content":"You are TerraWalk, a friendly world exploration assistant. Reply in the language the user uses. Be concise."},
            {"role":"user","content":f"Current map position: {body.lat}, {body.lon}. Request: {body.text}"}],"max_tokens":500})
    if r.status_code!=200: raise HTTPException(502,"Ошибка Groq API")
    return {"reply":r.json()["choices"][0]["message"]["content"]}

@app.post("/api/sky")
async def sky(body:Point):
    if not (CF_ACCOUNT and CF_KEY): raise HTTPException(503,"Добавьте CLOUDFLARE_ACCOUNT_ID и CLOUDFLARE_API_KEY в Render")
    prompt=f"Photorealistic cinematic 16:9 panoramic sky and distant horizon over the landscape near {body.name or f'{body.lat},{body.lon}'}, latitude {body.lat}, longitude {body.lon}, realistic local climate and season, natural clouds and atmospheric perspective, believable daylight, no text."
    url=f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    async with httpx.AsyncClient(timeout=90) as c:
        r=await c.post(url,headers={"Authorization":f"Bearer {CF_KEY}"},json={"prompt":prompt})
    if r.status_code!=200: raise HTTPException(502,"Cloudflare AI не смог создать небо; проверьте доступ к модели")
    image=r.json().get("result",{}).get("image")
    if not image: raise HTTPException(502,"Cloudflare вернул неизвестный формат")
    return {"image":image if image.startswith("data:") else "data:image/png;base64,"+image}

@app.get("/api/history")
async def history():
    col=history_collection()
    if col is None:return {"items":[],"enabled":False}
    try:
        rows=list(col.find({},{"_id":0,"name":1,"lat":1,"lon":1,"created_at":1}).sort("created_at",-1).limit(15))
        for x in rows:
            if x.get("created_at"):x["created_at"]=x["created_at"].isoformat()
        return {"items":rows,"enabled":True}
    except Exception:return {"items":[],"enabled":False}

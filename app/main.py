import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.routers import router as api_router

app = FastAPI(
    title="AssetVision OTG",
    description="Система автоматизованого фінансового аудиту громад",
    version="1.0.0"
)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["assetvision.org.ua", "*.assetvision.org.ua", "localhost", "127.0.0.1"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

media_root = Path(os.getenv("MEDIA_ROOT", "/app/media"))
media_root.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(media_root)), name="media")

templates = Jinja2Templates(directory="app/templates")

app.include_router(api_router)
@app.get("/", tags=["UI"])
async def read_root(request: Request):
    return templates.TemplateResponse(
        request=request,  # ОСЬ ЦЕЙ РЯДОК ОБОВ'ЯЗКОВИЙ
        name="index.html", 
        context={"request": request}
    )

@app.get("/login", tags=["UI"])
async def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,  # ТУТ ТЕЖ
        name="login.html", 
        context={"request": request}
    )

@app.get("/admin", tags=["UI"])
async def admin_page(request: Request):
    return templates.TemplateResponse(
        request=request, 
        name="admin.html", 
        context={"request": request}
    )

@app.get("/volunteer", tags=["UI"])
async def volunteer_page(request: Request):
    return templates.TemplateResponse(
        request=request, 
        name="activist.html", 
        context={"request": request}
    )

@app.get("/inspector", tags=["UI"])
async def inspector_view(request: Request):
    return templates.TemplateResponse(
        request=request, 
        name="inspector.html", 
        context={"request": request}
    )
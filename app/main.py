from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.routers import router as api_router
from app.core.config import settings

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

templates = Jinja2Templates(directory="app/templates")

app.include_router(api_router)

@app.get("/", tags=["UI"])
async def read_root(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"request": request},
    )

@app.get("/inspector", tags=["UI"])
async def inspector_view(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="inspector.html",
        context={"request": request},
    )

from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from backend.auth import ensure_local_user
from backend.config import settings
from backend.database import Base, SessionLocal, engine
from backend.middleware.rate_limit import limiter
from backend.routers import ai_assistant, campus, dashboard, internships, mailbox
from backend.ai_assistant_watcher import start_background_watcher, stop_background_watcher

Base.metadata.create_all(bind=engine)
_db_boot = SessionLocal()
try:
    ensure_local_user(_db_boot)
finally:
    _db_boot.close()

_is_prod = (getattr(settings, "ENV", "") or "").lower() == "production"


@asynccontextmanager
async def _app_lifespan(application: FastAPI):
    start_background_watcher()
    yield
    await stop_background_watcher()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    lifespan=_app_lifespan,
)
app.state.limiter = limiter


class StaticCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/static/"):
            if "cache-control" not in {k.lower() for k in response.headers}:
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


app.add_middleware(StaticCacheMiddleware)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "frontend", "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "frontend", "templates"))

app.include_router(internships.router)
app.include_router(campus.router)
app.include_router(dashboard.router)
app.include_router(mailbox.router)
app.include_router(ai_assistant.router)


def _page(request: Request, name: str, active: str, title: str):
    return templates.TemplateResponse(
        name,
        {
            "request": request,
            "active_page": active,
            "page_title": title,
            "offerflow_guard_json": "null",
        },
    )


@app.get("/")
def root():
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard")
def dashboard_page(request: Request):
    return _page(request, "dashboard.html", "dashboard", "工作台")


@app.get("/internships")
def internships_page(request: Request):
    return _page(request, "internships.html", "internships", "实习投递")


@app.get("/campus")
def campus_page(request: Request):
    return _page(request, "campus.html", "campus", "校招投递")


@app.get("/mail-read")
def mail_read_page(request: Request):
    return _page(request, "mail_read.html", "mail_read", "邮箱解析")


@app.get("/favicon.ico")
def favicon():
    return RedirectResponse(url="/static/logo/favicon.png")

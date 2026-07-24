# backend/app.py — DOM Hospitalist Nights (FacultyHubAdaptable instance)
#
# Trimmed entrypoint for the night-shift-only self-scheduling app.
# Only the routers this instance needs are wired up:
#   - auth, admin_auth          (login / password management)
#   - admin_faculty, admin_users (provider + user management)
#   - config                     (instance_config API)
#   - night_schedule              (admin: quarters, periods, builder, rebalancer)
#   - self_schedule                (provider: preferences grid)

import logging
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .models import SessionLocal, init_db, Base, engine, Faculty, get_db
from .auth import hash_password
from .config import settings
from .security import SecurityMiddleware, generate_secure_password

from .routes.auth import router as auth_router
from .routes.admin_auth import router as admin_auth_router
from .routes.admin_faculty import router as admin_faculty_router
from .routes.admin_users import router as admin_users_router
from .routes.config import router as config_router, seed_defaults as seed_config_defaults
from .routes.night_schedule import router as night_schedule_router
from .routes.self_schedule import router as self_schedule_router

logger = logging.getLogger(__name__)

# Create tables
Base.metadata.create_all(bind=engine)

# ---------- App Initialization -----------
app = FastAPI(title="DOM Night Scheduling")

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(SecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# ---------- Routers (before static/catch-all routes) -----------
app.include_router(auth_router)
app.include_router(admin_auth_router)
app.include_router(admin_faculty_router)
app.include_router(admin_users_router)
app.include_router(config_router)
app.include_router(night_schedule_router)
app.include_router(self_schedule_router)


# ---------- Startup -----------
@app.on_event("startup")
def startup_event():
    """Initialize database, seed config, and create the default admin user."""
    init_db()

    db = SessionLocal()
    try:
        seed_config_defaults(db)
        print("[Startup] Instance config defaults seeded")
    except Exception as e:
        print(f"[Startup] Config seed: {e}")
    finally:
        db.close()

    db = SessionLocal()
    try:
        admin_count = db.query(Faculty).filter_by(is_admin=True).count()
        if admin_count == 0:
            if settings.allows_default_admin() and settings.ADMIN_DEFAULT_PASSWORD:
                admin_password = settings.ADMIN_DEFAULT_PASSWORD
                print("[Startup] Using ADMIN_DEFAULT_PASSWORD from environment")
            else:
                admin_password = generate_secure_password()
                print("=" * 80)
                print("[Startup] GENERATED ADMIN PASSWORD (SAVE THIS IMMEDIATELY):")
                print("  Username: ADMIN")
                print(f"  Password: {admin_password}")
                print("=" * 80)
                print("This password will not be shown again!")
                print("Admin user must change password on first login.")
                print("=" * 80)

            admin = Faculty(
                id="ADMIN",
                name="Administrator",
                email=settings.ADMIN_EMAIL,
                is_admin=True,
                password_hash=hash_password(admin_password),
                password_changed=False,
                password_reset_required=True,
                registered=True,
                active=True,
                extra_config="{}",
            )
            db.add(admin)
            db.commit()

            if not settings.allows_default_admin():
                print("[Startup] Default admin login disabled in strict mode")
    except Exception as e:
        print(f"[Startup] Error creating admin user: {e}")
        db.rollback()
    finally:
        db.close()


# ========================================
# STATIC FILES — must come after API routers
# ========================================

ROOT_DIR = Path(__file__).resolve().parent.parent  # dom-night-scheduling/

if (ROOT_DIR / "icons").exists():
    app.mount("/icons", StaticFiles(directory=str(ROOT_DIR / "icons")), name="icons")

if (ROOT_DIR / "admin").exists():
    app.mount("/admin", StaticFiles(directory=str(ROOT_DIR / "admin"), html=True), name="admin")


@app.get("/")
async def serve_index():
    index_path = ROOT_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"status": "ok", "message": "DOM Night Scheduling API running"}


@app.get("/manifest.json")
async def serve_manifest():
    manifest_path = ROOT_DIR / "manifest.json"
    if manifest_path.exists():
        return FileResponse(manifest_path)
    raise HTTPException(status_code=404, detail="manifest.json not found")


@app.get("/style.css")
async def serve_style():
    css_path = ROOT_DIR / "style.css"
    if css_path.exists():
        response = FileResponse(css_path)
        response.headers["Cache-Control"] = "public, max-age=3600"
        return response
    raise HTTPException(status_code=404, detail="style.css not found")


@app.get("/favicon.svg")
async def serve_favicon_svg():
    favicon_path = ROOT_DIR / "favicon.svg"
    if favicon_path.exists():
        response = FileResponse(favicon_path, media_type="image/svg+xml")
        response.headers["Cache-Control"] = "public, max-age=86400"
        return response
    raise HTTPException(status_code=404, detail="favicon.svg not found")


@app.get("/{filename}.html")
async def serve_html_file(filename: str):
    """Serve any top-level HTML file (login.html, schedule.html, etc.)."""
    html_path = ROOT_DIR / f"{filename}.html"
    if html_path.exists():
        response = FileResponse(html_path)
        response.headers["Cache-Control"] = "public, max-age=3600"
        return response
    raise HTTPException(status_code=404, detail=f"{filename}.html not found")


@app.get("/{filename}.js")
async def serve_js_file(filename: str):
    """Serve any top-level JS file."""
    js_path = ROOT_DIR / f"{filename}.js"
    if js_path.exists():
        response = FileResponse(js_path, media_type="application/javascript")
        response.headers["Cache-Control"] = "public, max-age=3600"
        return response
    raise HTTPException(status_code=404, detail=f"{filename}.js not found")

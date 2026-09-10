from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import STATIC_DIR
from app.db.session import init_db
from app.routes.api import router as api_router
from app.routes.pages import router as pages_router
from scripts.generate_sample import generate_all_samples

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("depthwizard")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing DepthWizard Monorepo Service...")
    # Initialize SQLite tables
    init_db()
    # Generate starter samples if not present
    generate_all_samples()
    logger.info("DepthWizard ready to accept jobs.")
    yield
    logger.info("Shutting down DepthWizard.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="DepthWizard",
        description="Single-View Height Estimation & 3D Flythrough (ISRO SAC - SIH26175)",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS support
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Static assets mount (CSS, JS, 3D viewer)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Routers
    app.include_router(pages_router)
    app.include_router(api_router)

    return app


app = create_app()

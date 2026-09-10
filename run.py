#!/usr/bin/env python3
"""
DepthWizard: Single-Command Development Server Launcher
Usage:
    python run.py
    py -3.12 run.py --port 8080
"""
import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import HOST, PORT
from app.db.session import init_db
from scripts.generate_sample import generate_all_samples


def main():
    parser = argparse.ArgumentParser(description="DepthWizard Dev Server")
    parser.add_argument("--host", default=HOST, help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=PORT, help="Bind port (default: 8000)")
    parser.add_argument("--reload", action="store_true", default=True, help="Enable live auto-reload")
    args = parser.parse_args()

    print("=" * 65)
    print(" [*] DepthWizard - Single-View Height Estimation & 3D Flythrough")
    print("     ISRO SAC - Problem Statement SIH26175")
    print("=" * 65)
    print(" -> Initializing SQLite database...")
    init_db()

    print(" -> Checking sample optical test datasets...")
    generate_all_samples()

    print(f" -> Starting server at http://localhost:{args.port}/")
    print("    Press Ctrl+C to exit.")
    print("=" * 65)

    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()

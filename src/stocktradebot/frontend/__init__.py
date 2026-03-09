from __future__ import annotations

from pathlib import Path


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def find_frontend_dist() -> Path | None:
    dist_path = repository_root() / "frontend" / "dist"
    if (dist_path / "index.html").exists():
        return dist_path
    return None


def render_placeholder_html() -> str:
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>StockTradeBot</title>
    <style>
      :root { color-scheme: light; }
      body {
        margin: 0;
        font-family: "SF Mono", "Menlo", monospace;
        background: #ffffff;
        color: #111111;
      }
      main {
        max-width: 720px;
        margin: 0 auto;
        padding: 48px 24px;
      }
      h1, h2 { margin: 0 0 16px; }
      p { line-height: 1.6; }
      .card {
        border: 1px solid #111111;
        padding: 20px;
        margin-top: 24px;
      }
      code {
        background: #f4f4f4;
        padding: 2px 6px;
      }
    </style>
  </head>
  <body>
    <main>
      <h1>StockTradeBot Phase 1</h1>
      <p>
        The backend is running. The production frontend will live in
        <code>frontend/</code> and later phases will serve the built assets from here.
      </p>
      <div class="card">
        <h2>Available today</h2>
        <p>
          FastAPI runtime skeleton, SQLite bootstrap, Alembic migrations,
          CLI init/doctor/status, and CI/test baselines.
        </p>
      </div>
      <div class="card">
        <h2>API</h2>
        <p>Health endpoint: <code>/api/v1/health</code></p>
      </div>
    </main>
  </body>
</html>
"""

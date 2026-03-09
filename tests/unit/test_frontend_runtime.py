from __future__ import annotations

from pathlib import Path

from stocktradebot.frontend import find_frontend_dist


def test_find_frontend_dist_prefers_packaged_assets(tmp_path: Path) -> None:
    package_file = tmp_path / "site-packages" / "stocktradebot" / "frontend" / "__init__.py"
    package_file.parent.mkdir(parents=True)
    package_file.write_text("", encoding="utf-8")
    packaged_dist = package_file.parent / "dist"
    packaged_dist.mkdir()
    (packaged_dist / "index.html").write_text("<html>packaged</html>", encoding="utf-8")

    repository_dist = tmp_path / "frontend" / "dist"
    repository_dist.mkdir(parents=True)
    (repository_dist / "index.html").write_text("<html>repo</html>", encoding="utf-8")

    assert find_frontend_dist(module_file=package_file) == packaged_dist


def test_find_frontend_dist_falls_back_to_repository_assets(tmp_path: Path) -> None:
    module_file = tmp_path / "src" / "stocktradebot" / "frontend" / "__init__.py"
    module_file.parent.mkdir(parents=True)
    module_file.write_text("", encoding="utf-8")

    repository_dist = tmp_path / "frontend" / "dist"
    repository_dist.mkdir(parents=True)
    (repository_dist / "index.html").write_text("<html>repo</html>", encoding="utf-8")

    assert find_frontend_dist(module_file=module_file) == repository_dist

from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict[str, object]) -> None:
        frontend_dist = Path(self.root) / "frontend" / "dist"
        if not frontend_dist.is_dir():
            return

        target_path = "stocktradebot/frontend/dist"
        if self.target_name == "sdist":
            target_path = "frontend/dist"

        force_include = build_data.setdefault("force_include", {})
        if not isinstance(force_include, dict):
            return

        force_include[str(frontend_dist)] = target_path

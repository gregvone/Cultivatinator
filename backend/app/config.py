from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from .version import VERSION


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CULTIVATINATOR_")
    data_dir: Path = Path("../data")
    frontend_dir: Path = Path("../frontend/dist")
    environment: str = "development"

    @property
    def database_path(self) -> Path:
        return self.data_dir.resolve() / "database" / "cultivatinator.sqlite3"

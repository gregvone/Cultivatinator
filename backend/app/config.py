from pathlib import Path
from typing import Literal
from pydantic import model_validator

from pydantic_settings import BaseSettings, SettingsConfigDict

from .version import VERSION
from .backup_policy import BackupPolicy


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CULTIVATINATOR_")
    data_dir: Path = Path("../data")
    frontend_dir: Path = Path("../frontend/dist")
    environment: str = "development"
    maintenance_socket: Path = Path("/run/cultivatinator-maintenance/control.sock")
    maintenance_key: Path = Path("/run/cultivatinator-maintenance/channel.key")
    backup_auth_mode: Literal["password", "trusted_lan"] = "password"
    trusted_networks: str = ""

    @model_validator(mode="after")
    def validate_backup_policy(self):
        BackupPolicy(self.backup_auth_mode, self.trusted_networks)
        return self

    @property
    def database_path(self) -> Path:
        return self.data_dir.resolve() / "database" / "cultivatinator.sqlite3"

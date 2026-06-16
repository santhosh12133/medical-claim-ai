from pathlib import Path

from alembic import command
from alembic.config import Config


def bootstrap_database() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    command.upgrade(config, "head")


if __name__ == "__main__":
    bootstrap_database()
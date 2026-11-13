import importlib
import os


def test_empty_values_in_env_file_fall_back_to_defaults(monkeypatch):
    """Found when starting the app with a copied .env.example: empty lines must not break startup."""
    from app.core import config as config_module

    saved = {k: os.environ.get(k) for k in ("DATABASE_URL", "TOKEN_MINUTES", "CORS_ORIGINS")}
    for key in saved:
        monkeypatch.setenv(key, "")
    try:
        fresh = importlib.reload(config_module).Config
        assert fresh.database_url.startswith("sqlite:///") and fresh.database_url.endswith("creator_finder.db")
        assert fresh.token_minutes == 720 and "http://localhost:5173" in fresh.cors_origins
    finally:
        for key, value in saved.items():
            monkeypatch.setenv(key, value) if value is not None else monkeypatch.delenv(key, raising=False)
        importlib.reload(config_module)


def test_hosted_postgres_urls_use_the_installed_driver(monkeypatch):
    from app.core import config as config_module

    for given in ("postgres://u:p@host:5432/db?sslmode=require", "postgresql://u:p@host:5432/db?sslmode=require"):
        monkeypatch.setenv("DATABASE_URL", given)
        assert config_module._database_url() == "postgresql+psycopg://u:p@host:5432/db?sslmode=require"
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host/db")
    assert config_module._database_url() == "postgresql+psycopg://u:p@host/db"


def test_postgres_url_is_used_when_database_url_is_missing(monkeypatch):
    from app.core import config as config_module

    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("POSTGRES_URL", "postgres://u:p@host/db")
    assert config_module._database_url() == "postgresql+psycopg://u:p@host/db"

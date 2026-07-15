from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_env(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k] = v
    return env


@pytest.fixture
def db_conn():
    try:
        import psycopg2
    except ImportError:
        pytest.skip("psycopg2 no disponible")
    env = _load_env(REPO_ROOT / ".env")
    if not env.get("PGHOST"):
        pytest.skip("sin .env con credenciales PG")
    try:
        conn = psycopg2.connect(
            host=env["PGHOST"], port=env.get("PGPORT", "5432"),
            dbname=env["PGDATABASE"], user=env["PGUSER"], password=env["PGPASSWORD"],
        )
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no se pudo conectar a la BD: {exc}")
    conn.autocommit = False
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()

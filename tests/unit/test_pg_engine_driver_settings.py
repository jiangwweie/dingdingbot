from src.infrastructure.database import _build_pg_engine_kwargs


def test_asyncpg_uses_asyncpg_timeout_and_server_settings():
    connect_args = _build_pg_engine_kwargs("postgresql+asyncpg://example")[
        "connect_args"
    ]

    assert "command_timeout" in connect_args
    assert "server_settings" in connect_args
    assert "options" not in connect_args


def test_psycopg_uses_libpq_compatible_timeout_settings():
    connect_args = _build_pg_engine_kwargs("postgresql+psycopg://example")[
        "connect_args"
    ]

    assert "connect_timeout" in connect_args
    assert "options" in connect_args
    assert "command_timeout" not in connect_args
    assert "server_settings" not in connect_args

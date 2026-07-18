from __future__ import annotations

import ast

import sqlalchemy as sa

from scripts import reconcile_terminal_core_order_projection as repair


def _database_url(tmp_path) -> str:
    url = f"sqlite:///{tmp_path / 'terminal-core-orders.db'}"
    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(sa.text("CREATE TABLE orders (id TEXT PRIMARY KEY, symbol TEXT, order_role TEXT, status TEXT, exchange_order_id TEXT)"))
            conn.execute(sa.text("CREATE TABLE brc_ticket_bound_post_submit_closures (ticket_id TEXT, status TEXT, updated_at_ms INTEGER)"))
            conn.execute(sa.text("CREATE TABLE brc_ticket_bound_exit_protection_sets (ticket_id TEXT, symbol TEXT)"))
            conn.execute(sa.text("CREATE TABLE brc_ticket_bound_exit_protection_orders (ticket_id TEXT, local_order_id TEXT, exchange_order_id TEXT, role TEXT, status TEXT)"))
            conn.execute(sa.text("INSERT INTO orders VALUES ('core-sl', 'BTC/USDT:USDT', 'SL', 'OPEN', 'exchange-sl')"))
            conn.execute(sa.text("INSERT INTO brc_ticket_bound_post_submit_closures VALUES ('ticket-1', 'closed', 1234)"))
            conn.execute(sa.text("INSERT INTO brc_ticket_bound_exit_protection_sets VALUES ('ticket-1', 'BTC/USDT:USDT')"))
            conn.execute(sa.text("INSERT INTO brc_ticket_bound_exit_protection_orders VALUES ('ticket-1', 'core-sl', 'exchange-sl', 'SL', 'filled')"))
    finally:
        engine.dispose()
    return url


def test_terminal_core_order_repair_is_dry_run_by_default(tmp_path, capsys) -> None:
    url = _database_url(tmp_path)

    assert repair.main(["--database-url", url, "--allow-non-postgres-for-test"]) == 0

    result = ast.literal_eval(capsys.readouterr().out)
    assert result["status"] == "dry_run"
    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT status FROM orders")).scalar_one() == "OPEN"
    finally:
        engine.dispose()


def test_terminal_core_order_repair_applies_only_closed_exact_identity(tmp_path, capsys) -> None:
    url = _database_url(tmp_path)

    assert repair.main(["--database-url", url, "--allow-non-postgres-for-test", "--apply"]) == 0

    result = ast.literal_eval(capsys.readouterr().out)
    assert result["status"] == "applied"
    assert result["projected_count"] == 1
    assert result["exchange_write_called"] is False
    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT status FROM orders")).scalar_one() == "FILLED"
    finally:
        engine.dispose()


def test_terminal_core_order_repair_accepts_integer_closed_position_schema(
    tmp_path,
    capsys,
) -> None:
    url = _database_url(tmp_path)
    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "CREATE TABLE positions (symbol TEXT NOT NULL, is_closed INTEGER NOT NULL)"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO positions (symbol, is_closed) "
                    "VALUES ('BTC/USDT:USDT', 0)"
                )
            )

        assert repair.main(
            ["--database-url", url, "--allow-non-postgres-for-test", "--apply"]
        ) == 0
        blocked = ast.literal_eval(capsys.readouterr().out)
        assert blocked["projected_count"] == 0

        with engine.begin() as conn:
            conn.execute(sa.text("UPDATE positions SET is_closed = 1"))

        assert repair.main(
            ["--database-url", url, "--allow-non-postgres-for-test", "--apply"]
        ) == 0
        repaired = ast.literal_eval(capsys.readouterr().out)
        assert repaired["projected_count"] == 1
    finally:
        engine.dispose()

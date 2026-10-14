from pathlib import Path

import sqlalchemy as sa


async def apply_owner_control_grants(engine):
    sql=(Path(__file__).resolve().parents[3]/'deploy/owner-console/postgresql/owner-console-control-role.sql').read_text()
    grants='GRANT USAGE ON SCHEMA public TO brc_owner_control;'+sql.split('GRANT USAGE ON SCHEMA public TO brc_owner_control;',1)[1]
    async with engine.begin() as connection:
        exists=await connection.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='brc_owner_control')"))
        if not exists:await connection.execute(sa.text('CREATE ROLE brc_owner_control NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT'))
        for statement in grants.split(';'):
            if statement.strip():await connection.execute(sa.text(statement))

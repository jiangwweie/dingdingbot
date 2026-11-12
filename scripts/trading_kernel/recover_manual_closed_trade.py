#!/usr/bin/env python3
"""Exact recovery-only maintenance entry; signed GETs plus normal Kernel reductions."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT=Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0,str(REPO_ROOT))

from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.trading_kernel.application.management_intents import accepted_order_identities
from src.trading_kernel.application.readonly_closure_recovery import (
    recover_readonly_closure,
)
from src.trading_kernel.domain.product_identity import PRODUCT_ID
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.readonly_closure_source import (
    BinanceClosureReader,
    collect_readonly_closure,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION


def require_stopped_recovery_host(*,commit: str,machine_id: str) -> None:
    if os.geteuid()!=0 or Path('/etc/machine-id').read_text().strip()!=machine_id:
        raise ValueError('recovery host identity differs')
    if Path('/etc/brc/product-id').read_text().strip()!=PRODUCT_ID or not Path('/etc/brc/trading-kernel.write-fenced').is_file():
        raise ValueError('recovery product or fence differs')
    if Path('/opt/brc/current').resolve()!=REPO_ROOT or (REPO_ROOT/'.brc-runtime-commit').read_text().strip()!=commit:
        raise ValueError('recovery release identity differs')
    for role in ['observation','entry','lifecycle','reconciliation','api']:
        unit='brc-owner-console-api.service' if role=='api' else 'brc-trading-kernel-'+role+'-worker.service'
        if subprocess.run(['systemctl','is-active',unit],capture_output=True,timeout=10,check=False).returncode==0:
            raise ValueError('recovery requires all runtime writers stopped')


async def require_scope(c, *,commit: str,account_id: str,ticket_id: str) -> None:
    await c.execute(text("SET LOCAL statement_timeout='5s'"))
    state=(await c.execute(text("SELECT metadata_value FROM brc_schema_metadata WHERE metadata_key='runtime_commit'"))).scalar_one()
    rows=(await c.execute(text('SELECT * FROM brc_runtime_capabilities_current FOR UPDATE'))).mappings().all()
    paused=(await c.execute(text('SELECT NOT new_entry_submit_enabled FROM brc_owner_policy_current FOR UPDATE'))).scalar_one()
    actual=(await c.execute(text("SELECT DISTINCT account_id FROM brc_runtime_profiles WHERE environment='live' LIMIT 2"))).scalars().all()
    schema=(await c.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    if schema!=CURRENT_SCHEMA_REVISION or state!=commit or paused is not True or actual!=[account_id] or len(rows)!=2:
        raise ValueError('recovery source authority differs')
    for row in rows:
        cert=row['certification']
        if row['schema_revision']!=schema or row['enabled'] or row['certified_commit']!=commit or cert.get('product_id')!=PRODUCT_ID or cert.get('runtime_mode')!='management_recovery_only' or cert.get('management_recovery_ticket_ids')!=[ticket_id]:
            raise ValueError('recovery whitelist or disabled capability differs')


async def run(args) -> dict:
    root=Path('/etc/brc/manual-install')
    enrolled=json.loads((root/'verified-account.json').read_text())
    account=enrolled['account_id']
    secret=json.loads((root/'exchange-credentials.json').read_text())
    engine=create_async_engine((root/'admin-dsn').read_text().strip())
    try:
        async with PostgresKernelUnitOfWork(engine) as u:
            await require_scope(u._require_connection(),commit=args.commit,account_id=account,ticket_id=args.ticket_id)
            a=await u.aggregates.get(args.ticket_id)
            if a is None or a.identity.netting_domain.account_id!=account:
                raise ValueError('recovery Ticket differs')
            if a.status.value=='terminal':
                return {'status':'already_terminal','ticket_id':args.ticket_id}
            rows=await u.management.command_rows(args.ticket_id)
            entry=next((r for r in rows if r['command_kind']=='entry' and r['status'] in {'accepted','reconciled_accepted'}),None)
            if entry is None:
                raise ValueError('recovery entry missing')
            domain=a.identity.netting_domain
            since=a.ticket.created_at_ms
            order_id=entry['result_payload']['exchange_order_id']
            expected_version=a.version
        from src.trading_kernel.infrastructure.manual_account_setup import (
            BinanceManualAccountReader,
            ManualAccountCredentials,
            verify_manual_account,
        )
        credentials=ManualAccountCredentials(expected_uid=secret['expected_uid'],api_key=SecretStr(secret['api_key']),api_secret=SecretStr(secret['api_secret']),owner_username='readonly-recovery',owner_password=SecretStr('unused'))
        binding=await verify_manual_account(BinanceManualAccountReader(credentials),credentials)
        if not binding['account_ready'] or binding['credential_fingerprint']!=enrolled['credential_fingerprint']:
            raise ValueError('recovery exchange account binding or flatness differs')
        reader=BinanceClosureReader(api_key=SecretStr(secret['api_key']),api_secret=SecretStr(secret['api_secret']))
        proof=await asyncio.wait_for(collect_readonly_closure(reader,ticket_id=args.ticket_id,domain=domain,
            entry_order_id=order_id,own_orders=accepted_order_identities(rows),since_ms=since,clock_ms=lambda:int(time.time()*1000)),timeout=30)
        require_stopped_recovery_host(commit=args.commit,machine_id=args.machine_id)
        class PreviewRollback(Exception):
            pass
        try:
            async with PostgresKernelUnitOfWork(engine) as u:
                await require_scope(u._require_connection(),commit=args.commit,account_id=account,ticket_id=args.ticket_id)
                a=await u.aggregates.get_for_update(args.ticket_id)
                if a is None or a.version!=expected_version:
                    raise ValueError('recovery aggregate changed during readonly collection')
                await recover_readonly_closure(u,proof=proof,now_ms=int(time.time()*1000))
                if not args.apply:
                    raise PreviewRollback()
        except PreviewRollback:
            pass
        return {'status':'terminal' if args.apply else 'preview_pass','ticket_id':args.ticket_id,
            'proof_digest':proof.digest(),'venue_mutations':0,'economics':'net_unavailable_fees_and_funding',
            'observed_at_ms':proof.observed_at_ms}
    finally:
        await engine.dispose()


async def run_natural_exit(args) -> dict:
    from src.trading_kernel.application.verified_exit_closure import (
        settle_verified_exit,
    )
    from src.trading_kernel.infrastructure.manual_account_setup import (
        BinanceManualAccountReader,
        ManualAccountCredentials,
        verify_manual_account,
    )
    from src.trading_kernel.infrastructure.verified_exit_source import (
        collect_verified_exit,
    )
    root=Path('/etc/brc/manual-install');secret=json.loads((root/'exchange-credentials.json').read_text());enrolled=json.loads((root/'verified-account.json').read_text())
    credentials=ManualAccountCredentials(expected_uid=secret['expected_uid'],api_key=SecretStr(secret['api_key']),api_secret=SecretStr(secret['api_secret']),owner_username='readonly-recovery',owner_password=SecretStr('unused'))
    account=await verify_manual_account(BinanceManualAccountReader(credentials),credentials)
    if not account['account_ready'] or account['credential_fingerprint']!=enrolled['credential_fingerprint']:raise ValueError('natural recovery account identity or flatness differs')
    engine=create_async_engine((root/'admin-dsn').read_text().strip())
    async def scope(u):
        c=u._require_connection()
        rows=(await c.execute(text('SELECT * FROM brc_runtime_capabilities_current FOR UPDATE'))).mappings().all()
        schema=await c.scalar(text('SELECT version_num FROM alembic_version'))
        metadata_commit=await c.scalar(text("SELECT metadata_value FROM brc_schema_metadata WHERE metadata_key='runtime_commit'"))
        if metadata_commit!=args.commit:raise ValueError('natural recovery metadata identity differs')
        paused=await c.scalar(text('SELECT NOT new_entry_submit_enabled FROM brc_owner_policy_current FOR UPDATE'))
        if len(rows)!=2 or schema!=CURRENT_SCHEMA_REVISION or not paused:raise ValueError('natural recovery authority differs')
        for r in rows:
            cert=r['certification'];bound=cert.get('verified_exit_recovery_scope',{})
            if r['enabled'] or r['certified_commit']!=args.commit or r['schema_revision']!=schema or cert.get('product_id')!=PRODUCT_ID or cert.get('runtime_mode')!='verified_exit_recovery_only' or bound.get('ticket_id')!=args.ticket_id:raise ValueError('natural recovery identity or scope differs')
        exact=rows[0]['certification']['verified_exit_recovery_scope']
        if any(r['certification'].get('verified_exit_recovery_scope')!=exact for r in rows) or exact.get('target_commit')!=args.commit or exact.get('schema_revision')!=schema:raise ValueError('natural recovery scopes disagree')
        return exact
    try:
        async with PostgresKernelUnitOfWork(engine) as u:
            bound=await scope(u);a=await u.aggregates.get(args.ticket_id)
            if a is None or a.identity.netting_domain.account_id!=enrolled['account_id']:raise ValueError('natural recovery Ticket differs')
            if a.status.value=='terminal':return {'status':'already_terminal','ticket_id':args.ticket_id,'venue_mutations':0}
            if a.version!=bound['expected_version'] or a.management_revision!=bound['management_revision']:raise ValueError('natural recovery predecessor changed')
            refs=await u.exchange_commands.list_order_references(args.ticket_id)
        proof=await asyncio.wait_for(collect_verified_exit(BinanceClosureReader(api_key=SecretStr(secret['api_key']),api_secret=SecretStr(secret['api_secret'])),aggregate=a,references=refs,incident_ids=tuple(bound['incident_ids'])),timeout=60)
        if args.apply and args.expected_proof_digest!=proof.content_digest():raise ValueError('natural recovery preview facts changed')
        final_account=await verify_manual_account(BinanceManualAccountReader(credentials),credentials)
        if not final_account['account_ready'] or final_account['credential_fingerprint']!=enrolled['credential_fingerprint']:raise ValueError('natural recovery account changed during collection')
        require_stopped_recovery_host(commit=args.commit,machine_id=args.machine_id)
        class PreviewRollback(Exception):pass
        try:
            async with PostgresKernelUnitOfWork(engine) as u:
                await scope(u)
                await settle_verified_exit(u,proof=proof,now_ms=int(time.time()*1000))
                if not args.apply:raise PreviewRollback()
        except PreviewRollback:pass
        return {'status':'terminal' if args.apply else 'preview_pass','ticket_id':args.ticket_id,'proof_digest':proof.content_digest(),
            'verified_proof_digest':proof.digest(),'exit_reason':proof.exit_reason,'entry_quantity':str(proof.entry_quantity),'exit_quantity':str(proof.exit_quantity),
            'incident_ids':proof.incident_ids,'venue_mutations':0,'economics':'incomplete_evidence_fees_and_funding','observed_at_ms':proof.observed_at_ms}
    finally:await engine.dispose()


async def complete_natural_recovery(args) -> dict:
    from src.trading_kernel.infrastructure.manual_account_setup import (
        BinanceManualAccountReader,
        ManualAccountCredentials,
        verify_manual_account,
    )
    from src.trading_kernel.infrastructure.runtime_authority_seed import (
        RuntimeAuthoritySeedRequest,
        deploy_runtime_identity,
    )
    root=Path('/etc/brc/manual-install');secret=json.loads((root/'exchange-credentials.json').read_text());enrolled=json.loads((root/'verified-account.json').read_text())
    credentials=ManualAccountCredentials(expected_uid=secret['expected_uid'],api_key=SecretStr(secret['api_key']),api_secret=SecretStr(secret['api_secret']),owner_username='readonly-recovery',owner_password=SecretStr('unused'))
    facts=await verify_manual_account(BinanceManualAccountReader(credentials),credentials)
    if not facts['account_ready'] or facts['credential_fingerprint']!=enrolled['credential_fingerprint']:raise ValueError('normal recovery account identity or flatness differs')
    e=create_async_engine((root/'admin-dsn').read_text().strip())
    try:
        async with PostgresKernelUnitOfWork(e) as u:
            c=u._require_connection()
            rows=(await c.execute(text('SELECT * FROM brc_runtime_capabilities_current FOR UPDATE'))).mappings().all()
            if len(rows)!=2 or any(r['enabled'] or r['certified_commit']!=args.commit or r['certification'].get('runtime_mode')!='verified_exit_recovery_only' or r['certification'].get('verified_exit_recovery_scope',{}).get('ticket_id')!=args.ticket_id for r in rows):raise ValueError('completion recovery identity differs')
            paused=await c.scalar(text('SELECT NOT new_entry_submit_enabled FROM brc_owner_policy_current FOR UPDATE'))
            a=await u.aggregates.get(args.ticket_id)
            if not paused or a is None or a.status.value!='terminal':raise ValueError('completion needs Owner paused terminal source')
            await deploy_runtime_identity(u,RuntimeAuthoritySeedRequest(account_id=enrolled['account_id'],runtime_commit=args.commit,schema_revision=CURRENT_SCHEMA_REVISION,seeded_at_ms=int(time.time()*1000)))
        return {'status':'normal_identity_owner_paused','ticket_id':args.ticket_id,'venue_mutations':0}
    finally:await e.dispose()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--commit',required=True);p.add_argument('--machine-id',required=True)
    p.add_argument('--ticket-id',required=True);p.add_argument('--apply',action='store_true');p.add_argument('--natural-exit',action='store_true');p.add_argument('--expected-proof-digest');p.add_argument('--complete-recovery',action='store_true');args=p.parse_args()
    require_stopped_recovery_host(commit=args.commit,machine_id=args.machine_id)
    with open('/run/brc-manual-install.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        print(json.dumps(asyncio.run(complete_natural_recovery(args) if args.complete_recovery else run_natural_exit(args) if args.natural_exit else run(args))))


if __name__=='__main__':
    try:main()
    except Exception as exc:  # noqa: BLE001 - never emit credential-bearing tracebacks.
        print(json.dumps({'status':'blocked','error_type':type(exc).__name__,'detail':'sensitive output withheld; recovery fences retained'}));raise SystemExit(1) from None

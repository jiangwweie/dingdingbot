"""Exact Tokyo 0024 stopped recovery; GET proofs and normal Kernel events only."""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import subprocess
import time
from pathlib import Path

import sqlalchemy as sa
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import create_async_engine

from src.trading_kernel.application.verified_exit_closure import settle_verified_exit
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.readonly_closure_source import (
    BinanceClosureReader,
)
from src.trading_kernel.infrastructure.verified_exit_source import collect_verified_exit

MACHINE = "1c3442ab300e405e945a469ed8a12593"
SOURCE = "9190add529b8c40701a2ed83ca3aff722fee11a3"
SCHEMA = "0024_owner_cooperation"
ACCOUNT = "owner-subaccount-runtime-v0"
TICKET = "ticket:c7f8dbdb3702b84f555199f1118ea8be"
ROOT = Path(__file__).resolve().parents[2]


def validate_source(row):
    if (row['commit'], row['schema'], row['account'], row['policy'], row['entry']) != (SOURCE, SCHEMA, ACCOUNT, 3, False):
        raise ValueError('Tokyo recovery source identity or Owner pause changed')
    if row['tickets'] != [TICKET] or row['unknown'] or row['other_incidents']:
        raise ValueError('Tokyo recovery scope differs')


def stopped_host(tool_commit):
    if os.geteuid() != 0 or Path('/etc/machine-id').read_text().strip() != MACHINE:
        raise ValueError('Tokyo maintenance host differs')
    if Path('/etc/brc/product-id').read_text().strip() != 'brc-app-manual-v1' or not Path('/etc/brc/trading-kernel.write-fenced').is_file():
        raise ValueError('Tokyo maintenance product or fence differs')
    if Path('/opt/brc/current/.brc-runtime-commit').read_text().strip() != SOURCE:
        raise ValueError('Tokyo source release changed')
    if (ROOT/'.brc-runtime-commit').read_text().strip() != tool_commit:
        raise ValueError('Tokyo maintenance tool differs')
    from scripts.trading_kernel.certify_release_candidate import (
        ReleaseCertificationLevel,
        ReleaseCertificationManifest,
        validate_manifest_identity,
    )
    manifest = ReleaseCertificationManifest.model_validate_json((ROOT/'.brc-maintenance-certification.json').read_text())
    validate_manifest_identity(manifest, tool_commit, ReleaseCertificationLevel.R4)
    for unit in ['brc-owner-console-api.service', *[f'brc-trading-kernel-{r}-worker.service' for r in ['observation','entry','lifecycle','reconciliation']]]:
        if subprocess.run(['systemctl','is-active',unit],capture_output=True,timeout=10,check=False).returncode == 0:
            raise ValueError('Tokyo maintenance requires all five writers stopped')


async def source(c):
    await c.execute(sa.text("SET LOCAL statement_timeout='5s'"))
    row = (await c.execute(sa.text("""SELECT
    (SELECT metadata_value FROM brc_schema_metadata WHERE metadata_key='runtime_commit') commit,
    (SELECT version_num FROM alembic_version) schema,
    (SELECT account_id FROM brc_runtime_profiles WHERE runtime_profile_id='tiny-live-v1') account,
    (SELECT policy_version FROM brc_owner_policy_current) policy,
    (SELECT new_entry_submit_enabled FROM brc_owner_policy_current) entry,
    (SELECT array_agg(ticket_id ORDER BY ticket_id) FROM brc_trade_tickets WHERE terminal_at_ms IS NULL) tickets,
    EXISTS(SELECT 1 FROM brc_exchange_commands WHERE status IN ('prepared','claimed','dispatch_started','outcome_unknown')) unknown,
    EXISTS(SELECT 1 FROM brc_runtime_incidents WHERE status='open' AND (ticket_id IS DISTINCT FROM :ticket OR incident_kind<>'post_fill_risk_facts_unavailable')) other_incidents"""), {'ticket':TICKET})).mappings().one()
    validate_source(row)


async def run(tool_commit, apply):
    stopped_host(tool_commit)
    env = {}
    for line in Path('/etc/brc/trading-kernel.env').read_text().splitlines():
        k,v = line.split('=',1); env[k] = json.loads(v)
    from src.trading_kernel.infrastructure.manual_account_setup import (
        BinanceManualAccountReader,
        ManualAccountCredentials,
        verify_manual_account,
    )
    credentials = ManualAccountCredentials(expected_uid='1244153647',api_key=SecretStr(env['TRADING_KERNEL_API_KEY']),api_secret=SecretStr(env['TRADING_KERNEL_API_SECRET']),owner_username='readonly-maintenance',owner_password=SecretStr('unused'))
    account = await verify_manual_account(BinanceManualAccountReader(credentials),credentials)
    if not account['account_ready']:
        raise ValueError('Tokyo signed account not ready and flat')
    engine = create_async_engine(env['TRADING_KERNEL_DATABASE_URL'])
    class PreviewRollback(Exception):
        pass
    try:
        async with PostgresKernelUnitOfWork(engine) as u:
            await source(u._require_connection())
            a = await u.aggregates.get(TICKET)
            if a is None or (a.status.value,a.version,a.management_mode.value,a.post_fill_stress_status) != ('post_fill_risk_pending',4,'AUTO',None):
                raise ValueError('Tokyo exact aggregate predecessor changed')
            refs = await u.exchange_commands.list_order_references(TICKET)
            incidents = await u.incidents.list_open_for_ticket(TICKET)
        proof = await asyncio.wait_for(collect_verified_exit(BinanceClosureReader(api_key=credentials.api_key,api_secret=credentials.api_secret),aggregate=a,references=refs,incident_ids=tuple(i.incident_id for i in incidents)),timeout=60)
        if not proof.proves_full_initial_stop(entry_id=a.entry_exchange_order_id,stop_id=a.initial_stop_exchange_order_id):
            raise ValueError('Tokyo full original stop proof missing')
        stopped_host(tool_commit)
        replay = None
        try:
            async with PostgresKernelUnitOfWork(engine) as u:
                await source(u._require_connection())
                await settle_verified_exit(u,proof=proof,now_ms=int(time.time()*1000))
                scope = 'brc-app-manual-v1:binance-usdm:'+ACCOUNT
                await u.management.lock_receiver(scope)
                feed = await u.management.get_feed(scope,for_update=True)
                if feed is None or feed['persisted_watermark'] != 8 or feed['applied_watermark'] != 0:
                    raise ValueError('Tokyo exact management backlog changed')
                await u.management.persist_stream_batch(scope_key=scope,epoch_id=feed['epoch_id'],events=[],connected_at_ms=feed['connected_at_ms'],now_ms=int(time.time()*1000),gap_reason=feed['health_reason'],account_id=ACCOUNT,application_runtime_commit=tool_commit,replay_only=True)
                replay = await u.management.get_feed(scope)
                if replay['applied_watermark'] != replay['persisted_watermark']:
                    raise ValueError('Tokyo management replay incomplete')
                if not apply:
                    raise PreviewRollback
        except PreviewRollback:
            pass
        return {'status':'terminal' if apply else 'preview_pass','ticket_id':TICKET,'proof_digest':proof.digest(),'entry_quantity':str(proof.entry_quantity),'exit_quantity':str(proof.exit_quantity),'feed_applied':replay['applied_watermark'],'venue_mutations':0,'source_commit':SOURCE,'tool_commit':tool_commit}
    finally:
        await engine.dispose()


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tool-commit',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    with open('/run/brc-tokyo-maintenance.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        print(json.dumps(asyncio.run(run(args.tool_commit,args.apply))))

"""Explicit Tokyo manual-product upgrade profile; no fresh-install or alias bypass."""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

BINDING = {'machine_id':'1c3442ab300e405e945a469ed8a12593','account_id':'owner-subaccount-runtime-v0','database':'brc_trading_kernel','system_identifier':'7710109570187497514','uid':'1244153647'}
STATE = Path('/etc/brc/tokyo-manual-upgrade-20261123')
SOURCE = '9190add529b8c40701a2ed83ca3aff722fee11a3'


def validate_binding(row):
    if any(row.get(k) != v for k,v in BINDING.items()):
        raise ValueError('Tokyo manual upgrade identity differs')


def configure():
    """Bind installer transport/database configuration; retain every canonical gate."""
    from sqlalchemy.engine import make_url

    from scripts.trading_kernel import manual_host_bootstrap as bootstrap
    if os.geteuid()!=0 or Path('/etc/machine-id').read_text().strip()!=BINDING['machine_id']:
        raise ValueError('Tokyo upgrade requires bound root host')
    if Path('/etc/brc/product-id').read_text().strip()!='brc-app-manual-v1':
        raise ValueError('Tokyo upgrade product differs')
    env={k:json.loads(v) for line in Path('/etc/brc/trading-kernel.env').read_text().splitlines() for k,v in [line.split('=',1)]}
    url=make_url(env['TRADING_KERNEL_DATABASE_URL'])
    if url.host!='127.0.0.1' or url.port!=55433 or url.database!=BINDING['database'] or url.username!='brc_kernel' or env['TRADING_KERNEL_ACCOUNT_ID']!=BINDING['account_id']:
        raise ValueError('Tokyo upgrade retained environment differs')
    def read_database(query):
        return bootstrap.run(['docker','exec','brc-manual-runtime-pg','psql','-XqAt','-v','ON_ERROR_STOP=1','-U','brc_kernel','-d',BINDING['database'],'-c',"BEGIN READ ONLY; SET LOCAL statement_timeout='5s'; "+query+'; COMMIT;']).decode().strip()
    row=json.loads(read_database("SELECT json_build_object('machine_id','"+BINDING['machine_id']+"','account_id',(SELECT account_id FROM brc_runtime_profiles WHERE runtime_profile_id='tiny-live-v1'),'database',current_database(),'system_identifier',(SELECT system_identifier::text FROM pg_control_system()),'uid','"+BINDING['uid']+"')"))
    validate_binding(row)
    bootstrap.ROOT=STATE
    bootstrap.DATABASE=BINDING['database']
    bootstrap.read_database=read_database
    # These are explicit installation configuration seams. No schema, lifecycle,
    # certificate, pause, exposure, writer or history predicate is replaced.
    return bootstrap,env


async def prepare_credentials(bootstrap,env):
    from pydantic import SecretStr

    from src.trading_kernel.infrastructure.manual_account_setup import (
        BinanceManualAccountReader,
        ManualAccountCredentials,
        verify_manual_account,
    )
    credentials=ManualAccountCredentials(expected_uid=BINDING['uid'],api_key=SecretStr(env['TRADING_KERNEL_API_KEY']),api_secret=SecretStr(env['TRADING_KERNEL_API_SECRET']),owner_username='readonly-upgrade',owner_password=SecretStr('unused'))
    facts=await verify_manual_account(BinanceManualAccountReader(credentials),credentials)
    if not facts['account_ready']:
        raise ValueError('Tokyo signed account identity or flatness differs')
    STATE.mkdir(mode=0o700,parents=True,exist_ok=True)
    if STATE.is_symlink() or STATE.stat().st_mode & 0o077:
        raise ValueError('Tokyo installation state permissions differ')
    values={'admin-dsn':env['TRADING_KERNEL_DATABASE_URL']+'\n','exchange-credentials.json':json.dumps({'expected_uid':BINDING['uid'],'api_key':env['TRADING_KERNEL_API_KEY'],'api_secret':env['TRADING_KERNEL_API_SECRET']}),'verified-account.json':json.dumps({'account_id':BINDING['account_id'],'credential_fingerprint':facts['credential_fingerprint']})}
    for name,value in values.items():
        bootstrap.write_private(STATE/name,value)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase',required=True,choices=['stage','activate'])
    p.add_argument('--commit',required=True)
    p.add_argument('--sha256')
    args=p.parse_args()
    bootstrap,env=configure()
    with open('/run/brc-manual-install.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        from scripts.trading_kernel import manual_same_schema_upgrade as upgrade
        from scripts.trading_kernel.manual_upgrade_journal import UpgradeJournal
        if args.phase=='stage':
            source=bootstrap.require_stopped_upgrade()
            if source['commit']!=SOURCE or source['schema']!='0024_owner_cooperation':
                raise ValueError('Tokyo stopped source changed')
            asyncio.run(prepare_credentials(bootstrap,env))
            if not args.sha256:
                raise ValueError('Tokyo artifact digest required')
            receipt=bootstrap.receive_release(args.commit,args.sha256,sys.stdin.buffer,source_schema=source['schema'])
            bootstrap.write_private(STATE/'upgrade-source.json',json.dumps({'target_commit':args.commit,'source':source}),overwrite=True)
            print(json.dumps(receipt))
            return
        receipt=json.loads((STATE/'staged-release.json').read_text())
        prepared=json.loads((STATE/'upgrade-source.json').read_text())
        if receipt['commit']!=args.commit or prepared['target_commit']!=args.commit or Path(receipt['kernel_release']).resolve()!=ROOT:
            raise ValueError('Tokyo exact candidate binding differs')
        bootstrap.validate_certificates(json.loads((STATE/'certifications.json').read_text()),args.commit)
        journal=UpgradeJournal(STATE,receipt,prepared['source']) if (STATE/'upgrade-progress.json').exists() else None
        resume_binding=None if journal is None or journal.baseline is None else journal.resume_binding()
        observed=bootstrap.require_stopped_upgrade(resume_binding=resume_binding)
        if resume_binding is None and observed!=prepared['source']:
            raise ValueError('Tokyo stopped source drift')
        print(json.dumps(asyncio.run(upgrade.activate(receipt,prepared['source'],(STATE/'admin-dsn').read_text().strip()))))


if __name__=='__main__':
    try:
        main()
    except Exception as error:  # noqa: BLE001 - never expose credentials in child exceptions.
        import traceback
        print(json.dumps({'status':'blocked','error_type':type(error).__name__,'frames':[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(error.__traceback__)]}))
        raise SystemExit(1) from None

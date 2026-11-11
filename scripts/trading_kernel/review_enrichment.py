#!/usr/bin/env python3
"""Create/read an accounting preview; apply only an explicitly approved digest."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT=Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0,str(REPO_ROOT))

from sqlalchemy.ext.asyncio import create_async_engine

from src.trading_kernel.application.review_enrichment import (
    apply_review_enrichment,
    request_review_enrichment,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION


async def run(args):
    engine=create_async_engine(args.database_url)
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            profile=await uow.signals.get_runtime_profile('tiny-live-v1')
            capability=await uow.signals.get_runtime_capability('exchange_commands')
            if (profile is None or profile.account_id!=args.account_id or capability is None
                or capability.schema_revision!=CURRENT_SCHEMA_REVISION
                or capability.certified_commit!=args.runtime_commit
                or capability.certification.get('product_id')!='brc-app-manual-v1'):
                raise ValueError('account/runtime/schema identity differs')
            if args.action=='request':
                aggregate=await uow.aggregates.get(args.identity)
                if aggregate is None or aggregate.identity.netting_domain.account_id!=args.account_id:
                    raise ValueError('Ticket account identity differs')
                result={'request_id':await request_review_enrichment(uow,ticket_id=args.identity,now_ms=args.now_ms)}
            else:
                row=await uow.reviews.get_enrichment(args.identity)
                if row is None:
                    raise ValueError('enrichment request missing')
                aggregate=await uow.aggregates.get(row.ticket_id)
                if aggregate is None or aggregate.identity.netting_domain.account_id!=args.account_id:
                    raise ValueError('request account identity differs')
                if args.action=='apply':
                    if not args.approved_preview_digest or not args.owner_authorization_id:
                        raise ValueError('exact approved preview digest and genuine Owner authorization ID required')
                    result={'review_id':await apply_review_enrichment(uow,request_id=args.identity,
                        approved_preview_digest=args.approved_preview_digest,owner_authorization_id=args.owner_authorization_id,now_ms=args.now_ms)}
                else:
                    result=row.model_dump(mode="json")
        print(json.dumps(result,ensure_ascii=False,default=str))
    finally:
        await engine.dispose()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['request','preview','apply'])
    parser.add_argument('identity',help='exact Ticket ID for request, exact request ID otherwise')
    parser.add_argument('--database-url',required=True)
    parser.add_argument('--account-id',required=True)
    parser.add_argument('--runtime-commit',required=True)
    parser.add_argument('--now-ms',required=True,type=int)
    parser.add_argument('--approved-preview-digest')
    parser.add_argument('--owner-authorization-id')
    asyncio.run(run(parser.parse_args()))


if __name__=='__main__':
    main()

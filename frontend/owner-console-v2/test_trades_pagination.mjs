import assert from 'node:assert/strict';
import { QueryClient, InfiniteQueryObserver } from '@tanstack/react-query';
import { tradesPaginationOptions } from './src/api/tradesPagination.ts';
import { tradesMetricsEvidence } from './verification_contracts.mjs';
assert.equal(tradesMetricsEvidence([], {hasMore:true}).hasMore, true);
assert.equal(tradesMetricsEvidence([], {hasMore:false}).hasMore, false);
const requests=[];
let failSecond=true;
const fetchPage=async params=>{
  requests.push(params);
  if(params.cursor==='second' && failSecond) throw new Error('second page unavailable');
  return {data:{items: params.cursor ? [{ticket_id:'b',terminal_at_ms:1,net_pnl:{value:'-2'},net_r:{value:'-1'}}] : [{ticket_id:'a',terminal_at_ms:null}], next_cursor:params.cursor?null:'second'}};
};
const client=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0}}});
const observer=new InfiniteQueryObserver(client,tradesPaginationOptions({from_ms:10,to_ms:20,limit:1},fetchPage));
const unsubscribe=observer.subscribe(()=>{});
try {
 await observer.refetch();
 assert.equal(observer.getCurrentResult().hasNextPage,true);
 await observer.fetchNextPage();
 assert.equal(observer.getCurrentResult().isFetchNextPageError,true);
 assert.equal(observer.getCurrentResult().data.pages.length,1);
 assert.equal(observer.getCurrentResult().hasNextPage,true);
 failSecond=false;
 await observer.fetchNextPage();
 const result=observer.getCurrentResult();
 assert.equal(result.hasNextPage,false);
 assert.deepEqual(result.data.pages.flatMap(p=>p.data.items.map(t=>t.ticket_id)),['a','b']);
 assert.equal(result.isFetchNextPageError,false);
 assert.ok(requests.filter(p=>p.cursor==='second').length>=2);
 assert.ok(requests.every(p=>p.from_ms===10 && p.to_ms===20));
 const metrics=tradesMetricsEvidence(result.data.pages.flatMap(p=>p.data.items),{hasMore:result.hasNextPage});
 assert.equal(metrics.totalCount,2);
 assert.equal(metrics.formattedPnl,'-2.00 USDT');
 console.log('Pagination integration passed: cursor, fixed window, failure retention, retry, append, metrics');
} finally {unsubscribe();client.clear();}

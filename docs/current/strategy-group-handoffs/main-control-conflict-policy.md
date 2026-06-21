# Main-Control Conflict Policy

Status: CURRENT_PILOT_SUPPLEMENT
Last updated: 2026-06-15

## Policy

| Conflict | Rule |
| --- | --- |
| Same symbol, same side | Merge context and prepare at most one candidate. |
| Same symbol, opposite side | Block candidate preparation and require review. |
| Fresh signal with stale facts | Block candidate preparation. |
| Account position or open order conflict | Block candidate preparation. |
| Mark/funding abnormality | Downshift or block armed observation. |
| Observe-only group against armed group | Observe-only wins until facts pass. |

**Stale facts note:** In the current baseline, "stale facts" means upstream
freshness status/enum reports such as `stale`, `expired`, `outdated`, or
`STALE` — not numeric age comparison. Numeric freshness enforcement is a
deferred hardening option, not current baseline.

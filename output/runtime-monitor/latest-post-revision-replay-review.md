# BRF/LSR/VCB Post-Revision Replay Review

## Summary

- Status: `passed`
- Review cases: `8`
- Passed: `8`
- L2 promotion authority: `false`
- L4 scope change: `false`

## Review Rows

| StrategyGroup | Case | Signal | Side | Passed |
| --- | --- | --- | --- | --- |
| `BRF-001` | `bear_rally_failure_short_would_enter` | `would_enter` | `short` | `true` |
| `BRF-001` | `rally_extension_without_rejection_disabled` | `no_action` | `none` | `true` |
| `BRF-001` | `strong_uptrend_conflict_disabled` | `no_action` | `none` | `true` |
| `LSR-001` | `short_revival_short_would_enter` | `would_enter` | `short` | `true` |
| `LSR-001` | `old_long_preview_disabled` | `no_action` | `none` | `true` |
| `VCB-001` | `true_breakout_with_volume_would_enter` | `would_enter` | `long` | `true` |
| `VCB-001` | `false_breakout_reversal_disabled` | `no_action` | `none` | `true` |
| `VCB-001` | `volume_expansion_missing_disabled` | `no_action` | `none` | `true` |

## Next

- `record_brf001_lsr001_vcb001_post_revision_quality_before_l2`

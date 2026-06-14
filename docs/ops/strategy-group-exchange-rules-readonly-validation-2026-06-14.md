# Strategy Group Exchange Rules Read-Only Validation

Status: READ_ONLY_VALIDATION_PASS
Last updated: 2026-06-14

## Source

| Field | Value |
| --- | --- |
| Strategy handoff source commit | `05f616b0` |
| Exchange source | Binance USD-M Futures `GET /fapi/v1/exchangeInfo` |
| Validation mode | Read-only public exchange metadata |
| Account access | Not used |
| Exchange write | Not used |

## Summary

| Metric | Count |
| --- | ---: |
| Unique handoff symbols checked | `26` |
| Symbols currently `TRADING` | `26` |
| Missing symbols | `0` |
| Non-trading symbols | `0` |

## Symbol Rules Snapshot

| Symbol | Strategy Groups | Status | Min Notional | Qty Step | Price Tick |
| --- | --- | --- | ---: | ---: | ---: |
| `AMZNUSDT` | `MPG-001` | `TRADING` | `5` | `0.01` | `0.01000` |
| `AVGOUSDT` | `MPG-001` | `TRADING` | `5` | `0.01` | `0.01000` |
| `COINUSDT` | `FBS-001`, `MPG-001`, `TEQ-001` | `TRADING` | `5` | `0.01` | `0.01000` |
| `COPPERUSDT` | `PMR-001` | `TRADING` | `5` | `0.1` | `0.00100` |
| `CRCLUSDT` | `FBS-001`, `MPG-001`, `SOR-001`, `TEQ-001` | `TRADING` | `5` | `0.01` | `0.01000` |
| `EWYUSDT` | `MPG-001` | `TRADING` | `5` | `0.01` | `0.01000` |
| `FLNCUSDT` | `MPG-001` | `TRADING` | `5` | `0.01` | `0.01000` |
| `GOOGLUSDT` | `MPG-001` | `TRADING` | `5` | `0.01` | `0.01000` |
| `HOODUSDT` | `FBS-001`, `MPG-001`, `TEQ-001` | `TRADING` | `5` | `0.01` | `0.01000` |
| `INTCUSDT` | `FBS-001`, `MPG-001`, `SOR-001`, `TEQ-001` | `TRADING` | `5` | `0.01` | `0.01000` |
| `METAUSDT` | `MPG-001` | `TRADING` | `5` | `0.01` | `0.01000` |
| `MRVLUSDT` | `MPG-001`, `TEQ-001` | `TRADING` | `5` | `0.01` | `0.01000` |
| `MSTRUSDT` | `FBS-001`, `MPG-001`, `SOR-001`, `TEQ-001` | `TRADING` | `5` | `0.01` | `0.01000` |
| `MUUSDT` | `FBS-001`, `MPG-001`, `SOR-001`, `TEQ-001` | `TRADING` | `5` | `0.01` | `0.01000` |
| `NVDAUSDT` | `MPG-001`, `TEQ-001` | `TRADING` | `5` | `0.01` | `0.01000` |
| `PAXGUSDT` | `PMR-001` | `TRADING` | `5` | `0.001` | `0.0100` |
| `PLTRUSDT` | `MPG-001` | `TRADING` | `5` | `0.01` | `0.01000` |
| `SNDKUSDT` | `FBS-001`, `MPG-001`, `SOR-001`, `TEQ-001` | `TRADING` | `5` | `0.01` | `0.01000` |
| `SOXLUSDT` | `MPG-001` | `TRADING` | `5` | `0.01` | `0.01000` |
| `TSLAUSDT` | `MPG-001`, `TEQ-001` | `TRADING` | `5` | `0.01` | `0.01000` |
| `TSMUSDT` | `MPG-001` | `TRADING` | `5` | `0.01` | `0.01000` |
| `XAGUSDT` | `FBS-001`, `MPG-001`, `PMR-001`, `SOR-001` | `TRADING` | `5` | `0.001` | `0.0100` |
| `XAUTUSDT` | `PMR-001` | `TRADING` | `5` | `0.001` | `0.01` |
| `XAUUSDT` | `FBS-001`, `MPG-001`, `PMR-001`, `SOR-001` | `TRADING` | `5` | `0.001` | `0.01` |
| `XPDUSDT` | `PMR-001`, `SOR-001` | `TRADING` | `5` | `0.001` | `0.0100` |
| `XPTUSDT` | `PMR-001`, `SOR-001` | `TRADING` | `5` | `0.001` | `0.0100` |

## Boundary

This validation does not prove account readiness, position flatness,
open-order absence, protection readiness, margin safety, fresh strategy signal,
authorization evidence, FinalGate pass, or Operation Layer submit readiness.

It only removes the first exchange-rule blocker:

```text
exchange_symbol_rules_state: available_for_all_handoff_symbols
```

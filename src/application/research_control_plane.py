"""Application service for the Research Control Plane."""

from __future__ import annotations

import json
import os
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from src.application.research_specs import BacktestJobSpec, EngineCostSpec, TimeWindowMs
from src.domain.models import BacktestRequest, BacktestRuntimeOverrides, OrderStrategy
from src.domain.research_models import (
    CandidateRecord,
    CandidateReviewRequest,
    CreateCandidateRequest,
    ResearchJob,
    ResearchJobListResponse,
    ResearchJobStatus,
    ResearchRunListResponse,
    ResearchRunResult,
    ResearchSpec,
    utc_now_iso,
)
from src.infrastructure.logger import setup_logger
from src.infrastructure.research_repository import ResearchRepository

logger = setup_logger(__name__)

BacktestExecutor = Callable[[BacktestRequest, Optional[BacktestRuntimeOverrides]], Awaitable[object]]

BASELINE_PROFILE_ALIASES = {"backtest_eth_baseline", "sim1_eth_runtime"}

BASELINE_RUNTIME_OVERRIDES = BacktestRuntimeOverrides(
    max_atr_ratio=Decimal("0.01"),
    min_distance_pct=Decimal("0.005"),
    ema_period=50,
    tp_ratios=[Decimal("0.5"), Decimal("0.5")],
    tp_targets=[Decimal("1.0"), Decimal("3.5")],
    breakeven_enabled=False,
    allowed_directions=["LONG"],
)


class ResearchRunnerError(Exception):
    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code
        self.message = message


class LocalBacktestResearchRunner:
    """Runs one backtest job on the local process and writes artifacts."""

    def __init__(
        self,
        artifact_root: str = "reports/research_runs",
        backtest_executor: Optional[BacktestExecutor] = None,
    ):
        self.artifact_root = Path(artifact_root)
        self.backtest_executor = backtest_executor

    async def run(self, job: ResearchJob) -> ResearchRunResult:
        if self.backtest_executor is None:
            raise ResearchRunnerError("R-003", "No backtest executor is configured")

        run_dir = self.artifact_root / job.id
        run_dir.mkdir(parents=True, exist_ok=True)

        resolved_runtime_overrides = self._resolve_runtime_overrides(job.spec)
        request = self._to_backtest_request(job.spec, resolved_runtime_overrides)
        spec_snapshot = job.spec.model_dump(mode="json")
        if resolved_runtime_overrides is not None:
            spec_snapshot["resolved_runtime_overrides"] = resolved_runtime_overrides.model_dump(mode="json")
        if request.order_strategy is not None:
            spec_snapshot["resolved_order_strategy"] = request.order_strategy.model_dump(mode="json")
        spec_path = run_dir / "spec.json"
        self._write_json(spec_path, spec_snapshot)

        try:
            report = await self.backtest_executor(request, resolved_runtime_overrides)
        except ResearchRunnerError:
            raise
        except Exception as exc:
            raise ResearchRunnerError("R-003", str(exc)) from exc

        report_payload = self._model_to_payload(report)
        metrics = self._extract_summary_metrics(report_payload)

        result_path = run_dir / "result.json"
        metrics_path = run_dir / "metrics.json"
        self._write_json(result_path, report_payload)
        self._write_json(metrics_path, metrics)

        artifact_index = {
            "spec": str(spec_path),
            "result": str(result_path),
            "metrics": str(metrics_path),
        }
        result = ResearchRunResult(
            id=self._new_id("rr"),
            job_id=job.id,
            kind="backtest",
            spec_snapshot=spec_snapshot,
            summary_metrics=metrics,
            artifact_index=artifact_index,
            source_profile=job.spec.profile_name,
        )
        return result

    def _resolve_runtime_overrides(self, spec: ResearchSpec) -> Optional[BacktestRuntimeOverrides]:
        if spec.runtime_overrides is not None:
            return spec.runtime_overrides
        if spec.profile_name in BASELINE_PROFILE_ALIASES:
            return BASELINE_RUNTIME_OVERRIDES.model_copy(deep=True)
        return None

    def _to_backtest_request(
        self,
        spec: ResearchSpec,
        runtime_overrides: Optional[BacktestRuntimeOverrides],
    ) -> BacktestRequest:
        job_spec = BacktestJobSpec(
            name=spec.name,
            profile_name=spec.profile_name,
            symbol=spec.symbol,
            timeframe=spec.timeframe,
            window=TimeWindowMs(
                start_time_ms=spec.start_time_ms,
                end_time_ms=spec.end_time_ms,
            ),
            limit=spec.limit,
            mode=spec.mode,
            costs=EngineCostSpec(
                initial_balance=spec.costs.initial_balance,
                slippage_rate=spec.costs.slippage_rate,
                tp_slippage_rate=spec.costs.tp_slippage_rate,
                fee_rate=spec.costs.fee_rate,
            ),
            runtime_overrides=spec.runtime_overrides,
        )
        request = job_spec.to_backtest_request()
        if runtime_overrides and runtime_overrides.tp_ratios and runtime_overrides.tp_targets:
            request.order_strategy = OrderStrategy(
                id=f"{spec.profile_name}_order_strategy",
                name=f"{spec.profile_name} Order Strategy",
                tp_levels=len(runtime_overrides.tp_ratios),
                tp_ratios=runtime_overrides.tp_ratios,
                tp_targets=runtime_overrides.tp_targets,
                initial_stop_loss_rr=Decimal("-1.0"),
                trailing_stop_enabled=False,
                oco_enabled=True,
            )
        return request

    def _extract_summary_metrics(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "total_return": payload.get("total_return"),
            "max_drawdown": payload.get("max_drawdown"),
            "win_rate": payload.get("win_rate") or payload.get("simulated_win_rate"),
            "total_trades": payload.get("total_trades"),
            "sharpe_ratio": payload.get("sharpe_ratio"),
            "sortino_ratio": payload.get("sortino_ratio"),
            "total_pnl": payload.get("total_pnl"),
            "final_balance": payload.get("final_balance"),
        }

    def _model_to_payload(self, report: object) -> dict[str, Any]:
        if hasattr(report, "model_dump"):
            return report.model_dump(mode="json")
        if isinstance(report, dict):
            return report
        return {"raw": str(report)}

    def _write_json(self, path: Path, payload: object) -> None:
        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        except OSError as exc:
            raise ResearchRunnerError("R-004", str(exc)) from exc

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:16]}"


class ResearchJobService:
    def __init__(
        self,
        repository: ResearchRepository,
        runner: Optional[LocalBacktestResearchRunner] = None,
    ):
        self.repository = repository
        self.runner = runner

    async def create_backtest_job(self, spec: ResearchSpec) -> ResearchJob:
        job_id = self._new_id("rj")
        spec_ref = os.path.join("reports", "research_runs", job_id, "spec.json")
        job = ResearchJob(
            id=job_id,
            kind="backtest",
            name=spec.name,
            spec_ref=spec_ref,
            status=ResearchJobStatus.PENDING,
            spec=spec,
        )
        await self.repository.save_job(job)
        return job

    async def run_job(self, job_id: str) -> ResearchRunResult:
        if self.runner is None:
            raise ResearchRunnerError("R-003", "Research runner is not configured")

        job = await self.repository.get_job(job_id)
        if job is None:
            raise ResearchRunnerError("R-001", f"Research job not found: {job_id}")
        if job.status != ResearchJobStatus.PENDING:
            raise ResearchRunnerError("R-001", f"Research job is not pending: {job.status}")

        await self.repository.mark_job_running(job_id)
        running_job = await self.repository.get_job(job_id)
        try:
            result = await self.runner.run(running_job or job)
            await self.repository.save_run_result(result)
            await self.repository.mark_job_succeeded(job_id, result.id)
            return result
        except ResearchRunnerError as exc:
            await self.repository.mark_job_failed(job_id, exc.error_code, exc.message)
            raise
        except Exception as exc:
            await self.repository.mark_job_failed(job_id, "R-005", str(exc))
            raise

    async def list_jobs(
        self,
        status: Optional[ResearchJobStatus],
        limit: int,
        offset: int,
    ) -> ResearchJobListResponse:
        jobs, total = await self.repository.list_jobs(status=status, limit=limit, offset=offset)
        return ResearchJobListResponse(jobs=jobs, total=total, limit=limit, offset=offset)

    async def get_job(self, job_id: str) -> Optional[ResearchJob]:
        return await self.repository.get_job(job_id)

    async def get_run_result(self, result_id: str) -> Optional[ResearchRunResult]:
        return await self.repository.get_run_result(result_id)

    async def list_run_results(
        self,
        job_id: Optional[str],
        limit: int,
        offset: int,
    ) -> ResearchRunListResponse:
        runs, total = await self.repository.list_run_results(
            job_id=job_id,
            limit=limit,
            offset=offset,
        )
        return ResearchRunListResponse(runs=runs, total=total, limit=limit, offset=offset)

    async def create_candidate(self, request: CreateCandidateRequest) -> CandidateRecord:
        result = await self.repository.get_run_result(request.run_result_id)
        if result is None:
            raise ResearchRunnerError("R-001", f"Run result not found: {request.run_result_id}")
        now = utc_now_iso()
        candidate = CandidateRecord(
            id=self._new_id("cand"),
            run_result_id=request.run_result_id,
            candidate_name=request.candidate_name,
            review_notes=request.review_notes,
            created_at=now,
            updated_at=now,
        )
        await self.repository.save_candidate(candidate)
        return candidate

    async def list_candidates(
        self,
        status: Optional[object],
        limit: int,
        offset: int,
    ) -> tuple[list[CandidateRecord], int]:
        return await self.repository.list_candidates(status=status, limit=limit, offset=offset)

    async def get_candidate(self, candidate_id: str) -> Optional[CandidateRecord]:
        return await self.repository.get_candidate(candidate_id)

    async def review_candidate(
        self,
        candidate_id: str,
        request: CandidateReviewRequest,
    ) -> Optional[CandidateRecord]:
        candidate = await self.repository.get_candidate(candidate_id)
        if candidate is None:
            return None
        updated = candidate.model_copy(
            update={
                "status": request.status,
                "review_notes": request.review_notes,
                "applicable_market": request.applicable_market,
                "risks": request.risks,
                "recommendation": request.recommendation,
                "updated_at": utc_now_iso(),
            }
        )
        await self.repository.save_candidate(updated)
        return updated

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:16]}"

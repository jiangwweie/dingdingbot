"""
Strategy Optimizer - Optuna 集成自动化调参

功能：
1. 多目标优化（夏普比率、收益回撤比、索提诺比率、总收益）
2. 参数空间定义与采样
3. 异步优化执行
4. 断点续研支持

使用方式：
    optimizer = StrategyOptimizer(exchange_gateway, backtester)
    job = await optimizer.start_optimization(request)
    result = await optimizer.get_job_result(job_id)
"""
import asyncio
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Awaitable, Union
import logging
from concurrent.futures import ThreadPoolExecutor

from src.domain.models import (
    OptimizationRequest,
    OptimizationJob,
    OptimizationJobStatus,
    OptimizationTrialResult,
    OptimizationHistory,
    OptimizationObjective,
    OptunaDirection,
    ParameterSpace,
    ParameterType,
    BacktestRequest,
    PMSBacktestReport,
    BacktestRuntimeOverrides,
    RiskConfig,
)
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.application.backtester import Backtester
from src.application.backtest_config import (
    BacktestConfigResolver,
    DEFAULT_BACKTEST_PROFILE_PROVIDER,
    list_backtest_injectable_params,
)
from src.application.research_artifacts import get_git_metadata

logger = logging.getLogger(__name__)


OPTUNA_PARAM_TO_CONTRACT_KEY = {
    "max_atr_ratio": "strategy.atr.max_atr_ratio",
    "min_distance_pct": "strategy.ema.min_distance_pct",
    "ema_period": "strategy.ema.period",
    "mtf_ema_period": "system.mtf_ema_period",
    "tp_ratios": "execution.tp_ratios",
    "tp_targets": "execution.tp_targets",
    "breakeven_enabled": "backtest.breakeven_enabled",
    "same_bar_policy": "backtest.same_bar_policy",
    "same_bar_tp_first_prob": "backtest.same_bar_tp_first_prob",
    "random_seed": "backtest.random_seed",
    "allowed_directions": "backtest.allowed_directions",
    "max_loss_percent": "risk.max_loss_percent",
    "max_total_exposure": "risk.max_total_exposure",
}

OPTUNA_FIXED_PARAM_TO_CONTRACT_KEY = {
    **OPTUNA_PARAM_TO_CONTRACT_KEY,
    "max_leverage": "risk.max_leverage",
    "initial_balance": "backtest.initial_balance",
    "slippage_rate": "backtest.slippage_rate",
    "tp_slippage_rate": "backtest.tp_slippage_rate",
    "fee_rate": "backtest.fee_rate",
}

RISK_PARAM_NAMES = {"max_loss_percent", "max_total_exposure", "max_leverage"}
ENGINE_PARAM_NAMES = {"initial_balance", "slippage_rate", "tp_slippage_rate", "fee_rate"}


def json_dumps_safe(payload: Any, **kwargs: Any) -> str:
    """Dump JSON with Decimal/datetime safety for script/report artifacts."""
    import json

    return json.dumps(payload, ensure_ascii=False, default=str, **kwargs)


# ============================================================
# Optuna 导入（可选依赖）
# ============================================================
try:
    import optuna
    from optuna.trial import Trial
    from optuna.study import Study, StudyDirection
    OPTUNA_AVAILABLE = True
except ImportError:
    OPTUNA_AVAILABLE = False
    # 定义占位类型用于类型注解
    Study = Any
    Trial = Any
    StudyDirection = Any
    logger.warning("Optuna 未安装，请运行：pip install optuna>=3.5.0")


# ============================================================
# 性能计算工具类
# ============================================================

class PerformanceCalculator:
    """
    性能指标计算器

    提供多种优化目标的计算功能
    """

    @staticmethod
    def calculate_sharpe_ratio(
        returns: List[float],
        risk_free_rate: float = 0.0,
        periods_per_year: int = 252
    ) -> float:
        """
        计算夏普比率

        Args:
            returns: 收益率序列（小数形式，如 0.05 表示 5%）
            risk_free_rate: 无风险利率（年化）
            periods_per_year: 每年周期数（252 交易日）

        Returns:
            夏普比率
        """
        if len(returns) < 2:
            return 0.0

        import statistics

        # 计算平均收益和标准差
        mean_return = statistics.mean(returns)
        std_return = statistics.stdev(returns)

        if std_return == 0:
            return 0.0

        # 年化夏普比率
        annualized_return = mean_return * periods_per_year
        annualized_std = std_return * (periods_per_year ** 0.5)

        sharpe = (annualized_return - risk_free_rate) / annualized_std
        return sharpe

    @staticmethod
    def calculate_sortino_ratio(
        returns: List[float],
        risk_free_rate: float = 0.0,
        periods_per_year: int = 252
    ) -> float:
        """
        计算索提诺比率（只考虑下行波动）

        Args:
            returns: 收益率序列
            risk_free_rate: 无风险利率
            periods_per_year: 每年周期数

        Returns:
            索提诺比率
        """
        if len(returns) < 2:
            return 0.0

        import statistics

        mean_return = statistics.mean(returns)

        # 只计算负收益的标准差（下行偏差）
        downside_returns = [r for r in returns if r < 0]
        if len(downside_returns) < 2:
            return 0.0

        downside_std = statistics.stdev(downside_returns)

        if downside_std == 0:
            return 0.0

        annualized_return = mean_return * periods_per_year
        annualized_downside_std = downside_std * (periods_per_year ** 0.5)

        sortino = (annualized_return - risk_free_rate) / annualized_downside_std
        return sortino

    @staticmethod
    def calculate_max_drawdown(equity_curve: List[float]) -> float:
        """
        计算最大回撤

        Args:
            equity_curve: 资金曲线（累计值）

        Returns:
            最大回撤（绝对值，0.1 表示 10% 回撤）
        """
        if len(equity_curve) < 2:
            return 0.0

        peak = equity_curve[0]
        max_dd = 0.0

        for value in equity_curve:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, drawdown)

        return max_dd

    @staticmethod
    def calculate_pnl_dd_ratio(
        total_pnl: float,
        max_drawdown: float
    ) -> float:
        """
        计算收益回撤比

        Args:
            total_pnl: 总收益（绝对值）
            max_drawdown: 最大回撤

        Returns:
            收益回撤比
        """
        if max_drawdown == 0:
            return float('inf') if total_pnl > 0 else 0.0

        return total_pnl / max_drawdown


# ============================================================
# Strategy Optimizer 核心类
# ============================================================

class StrategyOptimizer:
    """
    策略参数优化器

    集成 Optuna 框架，支持多目标参数优化
    """

    # 线程池用于运行 Optuna 同步优化
    _executor = ThreadPoolExecutor(max_workers=4)

    def __init__(
        self,
        exchange_gateway: ExchangeGateway,
        backtester: Backtester,
        db_path: str = "data/optimization_history.db",
        backtest_config_resolver: Optional[BacktestConfigResolver] = None,
        backtest_profile_name: str = "backtest_eth_baseline",
    ):
        """
        初始化优化器

        Args:
            exchange_gateway: 交易所网关
            backtester: 回测引擎
            db_path: 优化历史数据库路径
        """
        self._gateway = exchange_gateway
        self._backtester = backtester
        self._db_path = db_path
        self._backtest_config_resolver = backtest_config_resolver or BacktestConfigResolver(
            DEFAULT_BACKTEST_PROFILE_PROVIDER
        )
        self._backtest_profile_name = backtest_profile_name

        # 任务管理
        self._jobs: Dict[str, OptimizationJob] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._stop_flags: Dict[str, bool] = {}

        # 固定参数存储（用于 Optuna 脚本传入）
        self._fixed_params: Dict[str, Dict[str, Any]] = {}

        # 性能计算器
        self._perf_calculator = PerformanceCalculator()

        # 优化历史仓库
        self._history_repo: Optional[OptimizationHistoryRepository] = None

        if not OPTUNA_AVAILABLE:
            logger.error("Optuna 未安装，请运行：pip install optuna>=3.5.0")

    async def initialize(self) -> None:
        """初始化优化历史仓库"""
        self._history_repo = OptimizationHistoryRepository(self._db_path)
        await self._history_repo.initialize()
        logger.info(f"优化历史仓库初始化完成：{self._db_path}")

    async def close(self) -> None:
        """关闭资源"""
        if self._history_repo:
            await self._history_repo.close()

    async def start_optimization(
        self,
        request: OptimizationRequest
    ) -> OptimizationJob:
        """
        启动优化任务

        Args:
            request: 优化请求

        Returns:
            优化任务对象
        """
        if not OPTUNA_AVAILABLE:
            raise RuntimeError("Optuna 未安装，请运行：pip install optuna>=3.5.0")
        self._validate_parameter_space(request.parameter_space)
        self._validate_fixed_params(request.fixed_params)

        # 生成任务 ID
        job_id = f"opt_{uuid.uuid4().hex[:8]}"

        # 创建任务对象
        job = OptimizationJob(
            job_id=job_id,
            request=request,
            status=OptimizationJobStatus.RUNNING,
            total_trials=request.n_trials,
            started_at=datetime.now(timezone.utc),
        )

        # 保存任务
        self._jobs[job_id] = job
        self._stop_flags[job_id] = False

        logger.info(f"创建优化任务：{job_id}, 目标={request.objective.value}, "
                   f"试验次数={request.n_trials}")

        # 启动异步优化任务
        task = asyncio.create_task(self._run_optimization(job_id, request))
        self._running_tasks[job_id] = task

        return job

    async def stop_optimization(self, job_id: str) -> None:
        """
        停止优化任务

        Args:
            job_id: 任务 ID

        Raises:
            ValueError: 任务不存在
        """
        if job_id not in self._jobs:
            raise ValueError(f"任务 {job_id} 不存在")

        # 设置停止标志
        self._stop_flags[job_id] = True

        # 取消正在运行的任务
        if job_id in self._running_tasks:
            task = self._running_tasks[job_id]
            if not task.done():
                task.cancel()
                logger.info(f"任务 {job_id}: 已取消")

        # 更新任务状态
        job = self._jobs[job_id]
        job.status = OptimizationJobStatus.STOPPED

        logger.info(f"任务 {job_id}: 已停止")

    async def _run_optimization(
        self,
        job_id: str,
        request: OptimizationRequest
    ) -> None:
        """
        运行优化任务（异步后台执行）

        Args:
            job_id: 任务 ID
            request: 优化请求
        """
        job = self._jobs[job_id]

        try:
            # 更新状态为运行中
            job.status = OptimizationJobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)

            # 创建 Optuna Study
            study = self._create_study(request)

            # 断点续研：加载历史试验
            # 简化版本，暂不实现
            # if request.resume_from_trial is not None and self._history_repo:
            #     await self._resume_study(study, job_id, request.resume_from_trial)

            # 定义目标函数（传入 fixed_params）
            objective_func = self._create_objective_function(
                request, job_id, fixed_params=request.fixed_params
            )

            # 运行优化（在线程中运行，避免与异步事件循环冲突）
            logger.info(f"任务 {job_id}: 开始优化，共 {request.n_trials} 次试验")

            callbacks = [self._create_trial_callback(job_id)]

            # 在线程池中运行 Optuna 的同步 optimize 方法
            loop = asyncio.get_event_loop()

            def _run_optimize():
                study.optimize(
                    objective_func,
                    n_trials=request.n_trials,
                    timeout=request.timeout,
                    callbacks=callbacks,
                    show_progress_bar=False,  # 在线程中禁用进度条
                )

            await loop.run_in_executor(self._executor, _run_optimize)

            # 更新任务状态为完成
            job.status = OptimizationJobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)

            # 保存最佳结果
            if study.best_trial:
                from src.domain.models import OptimizationTrialResult
                job.best_trial = OptimizationTrialResult(
                    trial_number=study.best_trial.number,
                    params=study.best_trial.params,
                    objective_value=study.best_value or 0.0,
                )
                job.best_value = study.best_value
                logger.info(f"任务 {job_id}: 优化完成，最佳目标值={study.best_value:.4f}")
                try:
                    candidate_path = await self.write_candidate_report(job_id)
                    logger.info(f"任务 {job_id}: candidate report written to {candidate_path}")
                except Exception as e:
                    logger.warning(f"任务 {job_id}: candidate report 写入失败: {e}", exc_info=True)

        except asyncio.CancelledError:
            # 任务被停止
            job.status = OptimizationJobStatus.STOPPED
            job.completed_at = datetime.now(timezone.utc)
            logger.info(f"任务 {job_id}: 被用户停止")
            self._stop_flags[job_id] = False  # 清除停止标志

        except Exception as e:
            # 任务失败
            job.status = OptimizationJobStatus.FAILED
            job.error_message = str(e)
            job.completed_at = datetime.now(timezone.utc)
            logger.error(f"任务 {job_id}: 失败 - {e}", exc_info=True)

        finally:
            # 清理运行中的任务
            if job_id in self._running_tasks:
                del self._running_tasks[job_id]
            # 清理停止标志
            if job_id in self._stop_flags:
                del self._stop_flags[job_id]

    def _create_study(
        self,
        request: OptimizationRequest
    ) -> Study:
        """
        创建 Optuna Study

        Args:
            request: 优化请求

        Returns:
            Optuna Study 对象
        """
        # 默认最大化所有目标
        direction = StudyDirection.MAXIMIZE

        study = optuna.create_study(
            direction=direction,
            study_name=f"optimization_{request.symbol}_{request.timeframe}",
            pruner=optuna.pruners.MedianPruner(n_startup_trials=10),
        )

        return study

    async def _resume_study(
        self,
        study: Study,
        job_id: str,
        resume_from: int
    ) -> None:
        """
        从历史试验恢复（断点续研）

        Args:
            study: Optuna Study 对象
            job_id: 任务 ID
            resume_from: 从第几个试验继续
        """
        if not self._history_repo:
            return

        # 加载历史试验记录
        trials = await self._history_repo.get_trials_by_job(job_id)

        for trial in trials:
            if trial.trial_number < resume_from:
                # 告诉 Optuna 这个试验已经完成
                study.tell(
                    trial.params,
                    trial.objective_value,
                )
                logger.debug(f"恢复试验 {trial.trial_number}: objective={trial.objective_value:.4f}")

        logger.info(f"任务 {job_id}: 从试验 {resume_from} 继续，已恢复 {len(trials)} 条历史记录")

    def _create_objective_function(
        self,
        request: OptimizationRequest,
        job_id: str,
        fixed_params: Optional[Dict[str, Any]] = None,
    ) -> Callable[[Trial], float]:
        """
        创建目标函数

        Args:
            request: 优化请求
            job_id: 任务 ID
            fixed_params: 固定参数（如 tp_ratios, tp_targets, breakeven_enabled）

        Returns:
            Optuna 目标函数
        """
        self._validate_parameter_space(request.parameter_space)
        self._validate_fixed_params(fixed_params)

        async def objective_async(trial: Trial) -> float:
            # 从参数空间采样
            params = self._sample_params(trial, request.parameter_space)

            # Phase 8.2: 构建 runtime_overrides，不再写 KV
            runtime_overrides = self._build_runtime_overrides(params, fixed_params)

            # 构建回测请求：以 backtest profile 为基线，而不是在 Optuna 内部硬编码策略/TP/风控。
            backtest_request, runtime_overrides = await self._build_trial_backtest_inputs(
                request,
                params,
                fixed_params,
                runtime_overrides,
            )

            # 运行回测（注入 runtime_overrides）
            report = await self._run_backtest(backtest_request, runtime_overrides)

            # 计算目标值
            objective_value = self._calculate_objective(
                request.objective,
                report,
            )

            # 记录试验历史
            if self._history_repo:
                history = self._build_optimization_history(
                    job_id=job_id,
                    trial_number=trial.number,
                    params=params,
                    objective_value=objective_value,
                    report=report,
                )
                await self._history_repo.save_trial(history)

            # 更新任务进度
            if job_id in self._jobs:
                self._jobs[job_id].current_trial = trial.number + 1

            return objective_value

        def objective(trial: Trial) -> float:
            # 检查停止标志
            if self._stop_flags.get(job_id, False):
                raise optuna.TrialPruned("任务被停止")

            # 运行异步目标函数
            # 由于 optimize 在线程中运行，这里可以安全地使用 asyncio.run
            return asyncio.run(objective_async(trial))

        return objective

    @staticmethod
    def _optimizer_safe_contract_keys() -> set[str]:
        return {param.key for param in list_backtest_injectable_params(optimizer_safe=True)}

    @staticmethod
    def _fixed_contract_keys() -> set[str]:
        return {param.key for param in list_backtest_injectable_params()}

    def _validate_parameter_space(self, parameter_space: ParameterSpace) -> None:
        """Ensure Optuna only samples explicitly optimizer-safe parameters."""
        optimizer_safe_keys = self._optimizer_safe_contract_keys()
        for param_def in parameter_space.parameters:
            contract_key = OPTUNA_PARAM_TO_CONTRACT_KEY.get(param_def.name)
            if contract_key is None:
                raise ValueError(f"Unsupported Optuna parameter: {param_def.name}")
            if contract_key not in optimizer_safe_keys:
                raise ValueError(f"Optuna parameter is not optimizer_safe: {param_def.name}")

    def _validate_fixed_params(self, fixed_params: Optional[Dict[str, Any]]) -> None:
        """Ensure fixed params are still declared in the injectable contract."""
        if not fixed_params:
            return
        contract_keys = self._fixed_contract_keys()
        for param_name in fixed_params:
            contract_key = OPTUNA_FIXED_PARAM_TO_CONTRACT_KEY.get(param_name)
            if contract_key is None:
                raise ValueError(f"Unsupported fixed parameter: {param_name}")
            if contract_key not in contract_keys:
                raise ValueError(f"Fixed parameter is not declared injectable: {param_name}")

    def _sample_params(
        self,
        trial: Trial,
        parameter_space: ParameterSpace
    ) -> Dict[str, Any]:
        """
        从参数空间采样

        Args:
            trial: Optuna Trial 对象
            parameter_space: 参数空间定义

        Returns:
            采样得到的参数字典
        """
        params = {}

        for param_def in parameter_space.parameters:
            if param_def.type == ParameterType.INT:
                params[param_def.name] = trial.suggest_int(
                    param_def.name,
                    int(param_def.low),
                    int(param_def.high),
                )
            elif param_def.type == ParameterType.FLOAT:
                # 浮点参数的 step 处理
                step = param_def.step if param_def.step is not None and param_def.step != 1 else None
                params[param_def.name] = trial.suggest_float(
                    param_def.name,
                    param_def.low_float,
                    param_def.high_float,
                    step=step,
                )
            elif param_def.type == ParameterType.CATEGORICAL:
                params[param_def.name] = trial.suggest_categorical(
                    param_def.name,
                    param_def.choices,
                )

        return params

    def _build_runtime_overrides(
        self,
        params: Dict[str, Any],
        fixed_params: Optional[Dict[str, Any]] = None,
    ) -> BacktestRuntimeOverrides:
        """
        从采样参数构建 BacktestRuntimeOverrides

        Phase 8.2: Optuna 接入参数链路
        - 支持 max_atr_ratio, min_distance_pct, ema_period
        - 不再依赖 SQLite KV 写入

        Args:
            params: 采样得到的参数字典
            fixed_params: 固定参数（如 tp_ratios, tp_targets, breakeven_enabled）

        Returns:
            BacktestRuntimeOverrides 对象
        """
        merged = {**params, **(fixed_params or {})}
        runtime_fields = set(BacktestRuntimeOverrides.model_fields)
        payload = {key: value for key, value in merged.items() if key in runtime_fields}
        return BacktestRuntimeOverrides(**payload)

    async def _build_trial_backtest_inputs(
        self,
        opt_request: OptimizationRequest,
        params: Dict[str, Any],
        fixed_params: Optional[Dict[str, Any]],
        runtime_overrides: BacktestRuntimeOverrides,
    ) -> tuple[BacktestRequest, BacktestRuntimeOverrides]:
        """
        Build trial inputs from the backtest profile baseline.

        Optuna can still override per-run fields, but the strategy/risk/execution
        baseline comes from BacktestConfigResolver.
        """
        request = self._build_profile_seed_request(opt_request, fixed_params)
        resolved = await self._backtest_config_resolver.resolve(
            self._backtest_profile_name,
            request=request,
            runtime_overrides=runtime_overrides,
        )

        risk_overrides = self._build_risk_overrides(
            params,
            fixed_params,
            fallback=resolved.risk_config,
        )
        final_request = resolved.to_backtest_request(request)
        if risk_overrides is not None:
            final_request = final_request.model_copy(update={"risk_overrides": risk_overrides}, deep=True)

        return final_request, runtime_overrides

    def _build_profile_seed_request(
        self,
        opt_request: OptimizationRequest,
        fixed_params: Optional[Dict[str, Any]] = None,
    ) -> BacktestRequest:
        """Build the minimal request that lets the profile fill strategy/risk/execution."""
        request_kwargs = {
            "symbol": opt_request.symbol,
            "timeframe": opt_request.timeframe,
            "start_time": opt_request.start_time,
            "end_time": opt_request.end_time,
            "limit": opt_request.limit,
            "mode": "v3_pms",
            "initial_balance": opt_request.initial_balance,
            "slippage_rate": opt_request.slippage_rate,
            "fee_rate": opt_request.fee_rate,
        }
        if fixed_params:
            for key in ENGINE_PARAM_NAMES:
                if key in fixed_params:
                    request_kwargs[key] = fixed_params[key]
        return BacktestRequest(**request_kwargs)

    def _build_risk_overrides(
        self,
        params: Dict[str, Any],
        fixed_params: Optional[Dict[str, Any]] = None,
        fallback: Optional[RiskConfig] = None,
    ) -> Optional[RiskConfig]:
        """Build RiskConfig overrides using profile risk as fallback."""
        risk_values: Dict[str, Any] = {}
        source = {**params, **(fixed_params or {})}
        for key in RISK_PARAM_NAMES:
            if key in source:
                risk_values[key] = source[key]
        if not risk_values:
            return None

        if fallback is None:
            raise ValueError("risk fallback is required to build Optuna risk overrides")
        base = fallback
        return RiskConfig(
            max_loss_percent=Decimal(str(risk_values.get("max_loss_percent", base.max_loss_percent))),
            max_leverage=int(risk_values.get("max_leverage", base.max_leverage)),
            max_total_exposure=Decimal(str(risk_values.get("max_total_exposure", base.max_total_exposure))),
            daily_max_trades=base.daily_max_trades,
            daily_max_loss=base.daily_max_loss,
        )

    async def _run_backtest(
        self,
        request: BacktestRequest,
        runtime_overrides: Optional[BacktestRuntimeOverrides] = None
    ) -> PMSBacktestReport:
        """
        运行回测

        Args:
            request: 回测请求
            runtime_overrides: 运行时参数覆盖（Phase 8.2）

        Returns:
            PMS 回测报告
        """
        report = await self._backtester.run_backtest(
            request,
            runtime_overrides=runtime_overrides,
        )
        return report

    def _calculate_objective(
        self,
        objective: OptimizationObjective,
        report: PMSBacktestReport
    ) -> float:
        """
        计算目标函数值

        Args:
            objective: 优化目标
            report: 回测报告

        Returns:
            目标函数值
        """
        if objective == OptimizationObjective.SHARPE:
            return float(report.sharpe_ratio) if report.sharpe_ratio else 0.0

        elif objective == OptimizationObjective.SORTINO:
            # 计算索提诺比率（如果需要可以从报告中计算）
            return float(report.sortino_ratio) if report.sortino_ratio else 0.0

        elif objective == OptimizationObjective.PNL_DD:
            # 收益回撤比
            total_pnl = float(report.total_pnl) if report.total_pnl else 0.0
            max_dd = float(report.max_drawdown) if report.max_drawdown else 0.0
            if max_dd == 0:
                return 0.0
            return total_pnl / max_dd

        elif objective == OptimizationObjective.TOTAL_RETURN:
            return float(report.total_return) if report.total_return else 0.0

        elif objective == OptimizationObjective.WIN_RATE:
            return float(report.win_rate) if report.win_rate else 0.0

        elif objective == OptimizationObjective.MAX_PROFIT:
            return float(report.total_pnl) if report.total_pnl else 0.0

        else:
            return 0.0

    def _create_trial_callback(
        self,
        job_id: str
    ) -> Callable[[Study, Trial], None]:
        """
        创建试验完成回调

        Args:
            job_id: 任务 ID

        Returns:
            回调函数
        """
        def callback(study: Study, trial: Trial) -> None:
            logger.info(
                f"任务 {job_id}: 试验 {trial.number} 完成，"
                f"objective={trial.value:.4f}"
            )
        return callback

    def _build_optimization_history(
        self,
        job_id: str,
        trial_number: int,
        params: Dict[str, Any],
        objective_value: float,
        report: PMSBacktestReport
    ) -> OptimizationHistory:
        """
        构建优化历史记录

        Args:
            job_id: 任务 ID
            trial_number: 试验编号
            params: 参数
            objective_value: 目标值
            report: 回测报告

        Returns:
            优化历史记录
        """
        import json

        # 构建指标字典
        metrics = {
            "total_return": float(report.total_return),
            "sharpe_ratio": float(report.sharpe_ratio) if report.sharpe_ratio else 0.0,
            "sortino_ratio": 0.0,  # 待实现
            "max_drawdown": float(report.max_drawdown),
            "win_rate": float(report.win_rate),
            "total_trades": report.total_trades,
            "total_pnl": float(report.total_pnl),
            "total_fees": float(report.total_fees_paid),
        }

        return OptimizationHistory(
            job_id=job_id,
            trial_number=trial_number,
            params_json=json.dumps(params),
            objective_value=objective_value,
            metrics_json=json.dumps(metrics),
            created_at=datetime.now(timezone.utc),
        )

    # ============================================================
    # 任务管理接口
    # ============================================================

    def get_job(self, job_id: str) -> Optional[OptimizationJob]:
        """获取任务详情"""
        return self._jobs.get(job_id)

    def list_jobs(
        self,
        status: Optional[OptimizationJobStatus] = None
    ) -> List[OptimizationJob]:
        """
        列出任务

        Args:
            status: 状态过滤（可选）

        Returns:
            任务列表
        """
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status == status]
        return jobs

    async def stop_job(self, job_id: str) -> bool:
        """
        停止优化任务

        Args:
            job_id: 任务 ID

        Returns:
            是否成功停止
        """
        if job_id not in self._running_tasks:
            return False

        # 设置停止标志
        self._stop_flags[job_id] = True
        logger.info(f"请求停止任务 {job_id}")

        # 等待任务结束
        try:
            self._running_tasks[job_id].cancel()
            await self._running_tasks[job_id]
        except asyncio.CancelledError:
            pass

        return True

    async def get_trial_results(
        self,
        job_id: str,
        limit: int = 100
    ) -> List[OptimizationTrialResult]:
        """
        获取试验结果

        Args:
            job_id: 任务 ID
            limit: 返回数量限制

        Returns:
            试验结果列表
        """
        import json

        if not self._history_repo:
            return []

        trials = await self._history_repo.get_trials_by_job(job_id, limit)

        results = []
        for t in trials:
            # 解析 JSON 字符串
            params = json.loads(t.params_json) if t.params_json else {}
            metrics = json.loads(t.metrics_json) if t.metrics_json else {}

            results.append(OptimizationTrialResult(
                trial_number=t.trial_number,
                params=params,
                objective_value=t.objective_value,
                total_return=metrics.get("total_return", 0.0),
                sharpe_ratio=metrics.get("sharpe_ratio", 0.0),
                sortino_ratio=metrics.get("sortino_ratio", 0.0),
                max_drawdown=metrics.get("max_drawdown", 0.0),
                win_rate=metrics.get("win_rate", 0.0),
                total_trades=metrics.get("total_trades", 0),
                datetime=t.created_at.isoformat() if hasattr(t.created_at, 'isoformat') else str(t.created_at),
            ))
        return results

    async def build_candidate_report(
        self,
        job_id: str,
        *,
        top_n: int = 5,
    ) -> Dict[str, Any]:
        """
        Build an Optuna candidate report without promoting it to runtime config.

        Candidate reports are the handoff artifact for manual review: they keep
        the source backtest profile hash, fixed params, best trial params, and
        the final request summary that would be used for a replay backtest.
        """
        job = self.get_job(job_id)
        if job is None:
            raise ValueError(f"Optimization job not found: {job_id}")

        results = await self.get_trial_results(job_id, limit=max(top_n, 1))
        ranked_results = sorted(results, key=lambda item: item.objective_value, reverse=True)
        best_trial = job.best_trial or (ranked_results[0] if ranked_results else None)
        if best_trial is None:
            raise ValueError(f"Optimization job has no completed trials: {job_id}")

        fixed_params = job.request.fixed_params or {}
        runtime_overrides = self._build_runtime_overrides(best_trial.params, fixed_params)
        seed_request = self._build_profile_seed_request(job.request, fixed_params)
        resolved = await self._backtest_config_resolver.resolve(
            self._backtest_profile_name,
            request=seed_request,
            runtime_overrides=runtime_overrides,
        )
        final_request, _ = await self._build_trial_backtest_inputs(
            job.request,
            best_trial.params,
            fixed_params,
            runtime_overrides,
        )

        repo_root = Path(__file__).resolve().parents[2]
        git_meta = get_git_metadata(repo_root)
        report_path = f"reports/optuna_candidates/optuna_candidate_{job_id}.json"

        return {
            "artifact_version": 1,
            "candidate_name": f"optuna_candidate_{job_id}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "candidate_only",
            "promotion_policy": "manual_review_required",
            "git": git_meta.to_dict(),
            "reproduce_cmd": f"PYTHONPATH=. python scripts/replay_optuna_candidate.py --candidate {report_path}",
            "source_profile": {
                "name": resolved.profile_name,
                "version": resolved.profile_version,
                "config_hash": resolved.config_hash,
            },
            "job": {
                "job_id": job_id,
                "status": job.status.value,
                "objective": job.request.objective.value,
                "symbol": job.request.symbol,
                "timeframe": job.request.timeframe,
                "start_time": job.request.start_time,
                "end_time": job.request.end_time,
                "n_trials": job.request.n_trials,
            },
            "best_trial": best_trial.model_dump(mode="json"),
            "fixed_params": fixed_params,
            "runtime_overrides": runtime_overrides.model_dump(mode="json", exclude_none=True),
            "constraints": {
                "allowed_directions": resolved.params.allowed_directions,
                "same_bar_policy": resolved.params.same_bar_policy,
                "random_seed": resolved.params.random_seed,
            },
            "resolved_request": {
                "symbol": final_request.symbol,
                "timeframe": final_request.timeframe,
                "limit": final_request.limit,
                "mode": final_request.mode,
                "initial_balance": final_request.initial_balance,
                "slippage_rate": final_request.slippage_rate,
                "tp_slippage_rate": final_request.tp_slippage_rate,
                "fee_rate": final_request.fee_rate,
                "risk_overrides": (
                    final_request.risk_overrides.model_dump(mode="json")
                    if final_request.risk_overrides
                    else None
                ),
                "order_strategy": (
                    final_request.order_strategy.model_dump(mode="json")
                    if final_request.order_strategy
                    else None
                ),
            },
            "top_trials": [trial.model_dump(mode="json") for trial in ranked_results[:top_n]],
        }

    async def write_candidate_report(
        self,
        job_id: str,
        *,
        output_dir: Union[str, Path] = "reports/optuna_candidates",
        top_n: int = 5,
    ) -> Path:
        """Write a candidate-only Optuna report to JSON and return its path."""
        report = await self.build_candidate_report(job_id, top_n=top_n)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        file_path = output_path / f"{report['candidate_name']}.json"
        file_path.write_text(
            json_dumps_safe(report, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return file_path


# ============================================================
# Optimization History Repository
# ============================================================

import aiosqlite
import os


class OptimizationHistoryRepository:
    """
    优化历史 SQLite 仓库

    持久化存储每次试验的参数和结果
    """

    def __init__(self, db_path: str = "data/optimization_history.db"):
        self._db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        self._owns_connection = True  # Marks whether this repo manages connection lifecycle

    async def initialize(self) -> None:
        """初始化数据库"""
        # 创建目录
        db_dir = os.path.dirname(self._db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        # 连接数据库 via connection pool (shared across repos)
        from src.infrastructure.connection_pool import get_connection as pool_get_connection
        self._db = await pool_get_connection(self._db_path)
        # PRAGMAs are set centrally in connection_pool, no need to repeat here

        # 创建表
        await self._create_tables()
        logger.info(f"优化历史仓库初始化完成：{self._db_path}")

    async def _create_tables(self) -> None:
        """创建数据表"""
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS optimization_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                trial_number INTEGER NOT NULL,

                -- 参数（JSON 格式）
                params TEXT NOT NULL,

                -- 目标值
                objective_value REAL NOT NULL,

                -- 回测指标
                total_return REAL DEFAULT 0.0,
                sharpe_ratio REAL DEFAULT 0.0,
                sortino_ratio REAL DEFAULT 0.0,
                max_drawdown REAL DEFAULT 0.0,
                win_rate REAL DEFAULT 0.0,
                total_trades INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0.0,
                total_fees REAL DEFAULT 0.0,

                -- 时间戳
                created_at TEXT NOT NULL,

                UNIQUE(job_id, trial_number)
            )
        """)

        # 创建索引
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_opt_history_job_id
            ON optimization_history(job_id)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_opt_history_trial
            ON optimization_history(job_id, trial_number)
        """)

        await self._db.commit()

    async def close(self) -> None:
        """Clear local connection reference (pool-managed connections are never closed by repos)."""
        if self._db:
            self._db = None

    async def save_trial(
        self,
        history: OptimizationHistory
    ) -> None:
        """
        保存试验记录

        Args:
            history: 优化历史记录
        """
        import json

        # 解析 metrics_json 获取详细指标
        metrics = json.loads(history.metrics_json)

        await self._db.execute("""
            INSERT OR REPLACE INTO optimization_history (
                job_id, trial_number, params,
                objective_value, total_return, sharpe_ratio, sortino_ratio,
                max_drawdown, win_rate, total_trades, total_pnl, total_fees,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            history.job_id,
            history.trial_number,
            history.params_json,
            history.objective_value,
            metrics.get("total_return", 0.0),
            metrics.get("sharpe_ratio", 0.0),
            metrics.get("sortino_ratio", 0.0),
            metrics.get("max_drawdown", 0.0),
            metrics.get("win_rate", 0.0),
            metrics.get("total_trades", 0),
            metrics.get("total_pnl", 0.0),
            metrics.get("total_fees", 0.0),
            history.created_at.isoformat() if hasattr(history.created_at, 'isoformat') else str(history.created_at),
        ))
        await self._db.commit()

    async def get_trials_by_job(
        self,
        job_id: str,
        limit: int = 1000
    ) -> List[OptimizationHistory]:
        """
        获取任务的试验历史

        Args:
            job_id: 任务 ID
            limit: 返回数量限制

        Returns:
            试验历史记录列表
        """
        import json

        cursor = await self._db.execute("""
            SELECT * FROM optimization_history
            WHERE job_id = ?
            ORDER BY trial_number
            LIMIT ?
        """, (job_id, limit))

        rows = await cursor.fetchall()
        results = []
        for row in rows:
            # 构建指标 JSON
            metrics = {
                "total_return": row["total_return"],
                "sharpe_ratio": row["sharpe_ratio"],
                "sortino_ratio": row["sortino_ratio"],
                "max_drawdown": row["max_drawdown"],
                "win_rate": row["win_rate"],
                "total_trades": row["total_trades"],
                "total_pnl": row["total_pnl"],
                "total_fees": row["total_fees"],
            }
            results.append(OptimizationHistory(
                id=row["id"],
                job_id=row["job_id"],
                trial_number=row["trial_number"],
                params_json=row["params"],
                objective_value=row["objective_value"],
                metrics_json=json.dumps(metrics),
                created_at=datetime.fromisoformat(row["created_at"]) if isinstance(row["created_at"], str) else row["created_at"],
            ))
        return results

    async def get_best_trial(
        self,
        job_id: str,
        direction: OptunaDirection = OptunaDirection.MAXIMIZE
    ) -> Optional[OptimizationHistory]:
        """
        获取最佳试验

        Args:
            job_id: 任务 ID
            direction: 优化方向

        Returns:
            最佳试验记录
        """
        trials = await self.get_trials_by_job(job_id, limit=10000)
        if not trials:
            return None

        if direction == OptunaDirection.MAXIMIZE:
            best = max(trials, key=lambda t: t.objective_value)
        else:
            best = min(trials, key=lambda t: t.objective_value)

        return best

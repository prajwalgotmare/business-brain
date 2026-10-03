"""Bounded live evaluation runner for the versioned golden dataset."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, ConfigDict, Field

from business_brain.agent.schemas import (
    AgentRoute,
    AgentRunResult,
    SupervisorIntent,
    WorkflowStatus,
)
from business_brain.agent.supervisor import GovernedSupervisor
from business_brain.api.dependencies import (
    get_analytics_service,
    get_generation_tracer,
    get_hybrid_retriever,
    get_llm_gateway,
)
from business_brain.core.config import Settings, get_settings
from business_brain.evaluation.models import (
    EvaluationCategory,
    GoldenEvaluationCase,
    GoldenEvaluationManifest,
)
from business_brain.evaluation.scoring import (
    CaseScore,
    EvaluationMetrics,
    EvaluationObservation,
    aggregate_metrics,
)
from business_brain.security.context import AuthContext


class EvaluationThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    routing_accuracy: float = Field(default=0.85, ge=0, le=1)
    permission_accuracy: float = Field(default=1.0, ge=0, le=1)
    citation_recall: float = Field(default=0.85, ge=0, le=1)
    action_policy_accuracy: float = Field(default=1.0, ge=0, le=1)
    task_success_rate: float = Field(default=0.80, ge=0, le=1)
    ragas_groundedness: float = Field(default=0.85, ge=0, le=1)


class EvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    generated_at: datetime
    dataset_version: str
    primary_model: str
    fallback_model: str
    judge_model: str | None
    ragas_enabled: bool
    thresholds: EvaluationThresholds
    threshold_results: dict[str, bool]
    metrics: EvaluationMetrics
    scores: list[CaseScore]
    observations: list[EvaluationObservation]


def load_golden_manifest(path: Path) -> GoldenEvaluationManifest:
    return GoldenEvaluationManifest.model_validate_json(path.read_text(encoding="utf-8"))


def build_evaluation_supervisor(settings: Settings) -> GovernedSupervisor:
    return GovernedSupervisor(
        gateway=get_llm_gateway(),
        tracer=get_generation_tracer(),
        primary_model=settings.groq_primary_model,
        analytics_service=get_analytics_service(),
        retriever=get_hybrid_retriever(),
        checkpointer=InMemorySaver(),
    )


def _jsonable(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return None


def observation_from_result(
    case: GoldenEvaluationCase,
    result: AgentRunResult,
    *,
    latency_ms: float,
) -> EvaluationObservation:
    contexts: list[str] = []
    if case.category == EvaluationCategory.DOCUMENT_RETRIEVAL:
        for item in result.tool_result or []:
            if isinstance(item, dict) and isinstance(item.get("content"), str):
                contexts.append(item["content"])
    return EvaluationObservation(
        case_id=case.case_id,
        answer=result.answer,
        route=result.route,
        intent=result.intent,
        status=result.status,
        tool_name=result.tool_name,
        error_code=result.error_code,
        citations=result.citations,
        action_draft=_jsonable(result.action_draft),
        approval=_jsonable(result.approval),
        structured_evidence=result.tool_result,
        retrieved_contexts=contexts,
        prompt_tokens=result.usage.prompt_tokens,
        completion_tokens=result.usage.completion_tokens,
        total_tokens=result.usage.total_tokens,
        latency_ms=latency_ms,
        model=result.model,
        provider=result.provider,
        used_fallback=result.used_fallback,
        attempt_count=result.attempt_count,
    )


def failed_observation(
    case: GoldenEvaluationCase, exc: Exception, *, latency_ms: float
) -> EvaluationObservation:
    return EvaluationObservation(
        case_id=case.case_id,
        answer="Evaluation case failed before a governed result was returned.",
        route=AgentRoute.REFUSE,
        intent=SupervisorIntent.UNSUPPORTED,
        status=WorkflowStatus.FAILED,
        latency_ms=latency_ms,
        runtime_error=type(exc).__name__,
    )


async def run_agent_case(
    supervisor: GovernedSupervisor,
    case: GoldenEvaluationCase,
    *,
    max_tokens: int,
) -> EvaluationObservation:
    started = perf_counter()
    try:
        result = await supervisor.run(
            request_id=f"eval-{case.case_id}-{uuid4().hex[:8]}",
            thread_id=f"eval-{case.case_id}-{uuid4().hex}",
            auth=AuthContext(
                tenant_id=case.tenant_id,
                user_id=f"eval-{case.role.value}",
                role=case.role,
            ),
            question=case.question,
            max_tokens=max_tokens,
        )
        return observation_from_result(
            case,
            result,
            latency_ms=(perf_counter() - started) * 1_000,
        )
    except Exception as exc:
        return failed_observation(
            case,
            exc,
            latency_ms=(perf_counter() - started) * 1_000,
        )


async def add_ragas_scores(
    cases: list[GoldenEvaluationCase],
    observations: list[EvaluationObservation],
    settings: Settings,
    *,
    delay_seconds: float = 0,
) -> None:
    if not settings.groq_api_key:
        raise ValueError("GROQ_API_KEY is required for RAGAS judging")

    from langchain_openai import ChatOpenAI
    from ragas import SingleTurnSample
    from ragas.metrics import Faithfulness

    judge = ChatOpenAI(
        model=settings.groq_fallback_model,
        api_key=settings.groq_api_key,
        base_url=str(settings.groq_base_url),
        timeout=settings.llm_timeout_seconds,
        temperature=0,
        max_completion_tokens=800,
        max_retries=1,
    )
    faithfulness = Faithfulness(llm=judge)
    by_id = {case.case_id: case for case in cases}

    for observation in observations:
        case = by_id[observation.case_id]
        if (
            case.category != EvaluationCategory.DOCUMENT_RETRIEVAL
            or observation.runtime_error
            or not observation.retrieved_contexts
        ):
            continue
        sample = SingleTurnSample(
            user_input=case.question,
            retrieved_contexts=observation.retrieved_contexts,
            response=observation.answer,
            reference=case.expected_summary,
        )
        try:
            observation.ragas_faithfulness = await faithfulness.single_turn_ascore(
                sample
            )
        except Exception as exc:
            observation.runtime_error = f"ragas:{type(exc).__name__}"
        if delay_seconds:
            await asyncio.sleep(delay_seconds)


def threshold_results(
    metrics: EvaluationMetrics,
    thresholds: EvaluationThresholds,
    *,
    require_ragas: bool,
) -> dict[str, bool]:
    results = {
        "routing_accuracy": metrics.routing_accuracy >= thresholds.routing_accuracy,
        "permission_accuracy": (
            metrics.permission_accuracy >= thresholds.permission_accuracy
        ),
        "citation_recall": metrics.citation_recall >= thresholds.citation_recall,
        "action_policy_accuracy": (
            metrics.action_policy_accuracy >= thresholds.action_policy_accuracy
        ),
        "task_success_rate": metrics.task_success_rate >= thresholds.task_success_rate,
    }
    if require_ragas:
        results["ragas_groundedness"] = bool(
            metrics.ragas_groundedness is not None
            and metrics.ragas_groundedness >= thresholds.ragas_groundedness
        )
    return results


async def run_evaluation(
    manifest: GoldenEvaluationManifest,
    *,
    case_limit: int | None = None,
    case_ids: set[str] | None = None,
    enable_ragas: bool = True,
    max_tokens: int = 700,
    case_delay_seconds: float = 0,
    ragas_delay_seconds: float = 0,
) -> EvaluationReport:
    settings = get_settings()
    cases = (
        [case for case in manifest.cases if case.case_id in case_ids]
        if case_ids
        else manifest.cases
    )
    cases = cases[:case_limit] if case_limit else cases
    if not cases:
        raise ValueError("evaluation selection contains no golden cases")
    supervisor = build_evaluation_supervisor(settings)
    observations = []
    for index, case in enumerate(cases):
        observations.append(await run_agent_case(supervisor, case, max_tokens=max_tokens))
        if case_delay_seconds and index < len(cases) - 1:
            await asyncio.sleep(case_delay_seconds)
    if enable_ragas:
        await add_ragas_scores(
            cases,
            observations,
            settings,
            delay_seconds=ragas_delay_seconds,
        )
    metrics, scores = aggregate_metrics(cases, observations)
    thresholds = EvaluationThresholds()
    return EvaluationReport(
        generated_at=datetime.now(UTC),
        dataset_version=manifest.dataset_version,
        primary_model=settings.groq_primary_model,
        fallback_model=settings.groq_fallback_model,
        judge_model=settings.groq_fallback_model if enable_ragas else None,
        ragas_enabled=enable_ragas,
        thresholds=thresholds,
        threshold_results=threshold_results(
            metrics,
            thresholds,
            require_ragas=enable_ragas,
        ),
        metrics=metrics,
        scores=scores,
        observations=observations,
    )


def write_report(report: EvaluationReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )


def run_sync(*args: Any, **kwargs: Any) -> EvaluationReport:
    return asyncio.run(run_evaluation(*args, **kwargs))

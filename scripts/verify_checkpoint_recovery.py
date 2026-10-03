"""Prove a pending LangGraph approval survives a Neon connection/process restart."""

from __future__ import annotations

import asyncio
import json
import sys
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from business_brain.agent.approvals import ApprovalDecision
from business_brain.agent.supervisor import GovernedSupervisor
from business_brain.api.dependencies import (
    start_agent_checkpoint_runtime,
    stop_agent_checkpoint_runtime,
)
from business_brain.core.config import Settings
from business_brain.llm.schemas import GenerationRequest, GenerationResult
from business_brain.observability.tracing import NoOpGenerationTracer
from business_brain.security.context import AuthContext, UserRole

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "data" / "quality" / "checkpoint_recovery_smoke.json"


class StubGateway:
    def __init__(self, responses: list[GenerationResult]) -> None:
        self.responses = deque(responses)
        self.call_count = 0

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        del request
        self.call_count += 1
        if not self.responses:
            raise AssertionError("LLM must not be called while resuming a checkpoint")
        return self.responses.popleft()


def _generation(content: str) -> GenerationResult:
    return GenerationResult(content=content, model="checkpoint-verification-stub")


def _route() -> str:
    return json.dumps(
        {
            "route": "action_drafting",
            "intent": "draft_purchase_order",
            "risk_level": "high",
            "rationale": "Purchase order requested",
            "confidence": 1,
            "arguments": {},
        }
    )


def _purchase_order() -> str:
    return json.dumps(
        {
            "supplier_id": "sup_aur_packaging",
            "warehouse_id": "wh_aur_west",
            "expected_delivery_date": "2026-10-15",
            "currency_code": "USD",
            "lines": [
                {
                    "product_id": "prd_aur_006",
                    "sku": "AUR-SKN-006",
                    "quantity": 300,
                    "unit_cost": "11.37",
                    "line_amount": "3411.00",
                }
            ],
            "subtotal_amount": "3411.00",
            "tax_amount": "0.00",
            "freight_amount": "125.00",
            "total_amount": "3536.00",
            "notes": "Restart recovery verification",
        }
    )


def _supervisor(gateway: StubGateway, saver: AsyncPostgresSaver) -> GovernedSupervisor:
    return GovernedSupervisor(
        gateway=gateway,
        tracer=NoOpGenerationTracer(),
        primary_model="checkpoint-verification-stub",
        checkpointer=saver,
    )


async def verify() -> dict[str, object]:
    settings = Settings()
    url = settings.database_url or settings.database_url_direct
    if not url:
        raise RuntimeError("DATABASE_URL or DATABASE_URL_DIRECT must be configured")
    await start_agent_checkpoint_runtime()
    await stop_agent_checkpoint_runtime()
    thread_id = str(uuid4())
    logistics = AuthContext(
        tenant_id="tenant_aura",
        user_id="restart-logistics",
        role=UserRole.LOGISTICS_MANAGER,
    )
    cfo = AuthContext(
        tenant_id="tenant_aura",
        user_id="restart-cfo",
        role=UserRole.FOUNDER_CFO,
    )
    first_gateway = StubGateway([_generation(_route()), _generation(_purchase_order())])
    async with AsyncPostgresSaver.from_conn_string(url) as first_saver:
        await first_saver.setup()
        pending = await _supervisor(first_gateway, first_saver).run(
            request_id=str(uuid4()),
            thread_id=thread_id,
            auth=logistics,
            question="Draft the locked replenishment purchase order",
            max_tokens=512,
        )
    if pending.status.value != "pending_approval":
        raise AssertionError("workflow did not reach pending approval")

    second_gateway = StubGateway([])
    async with AsyncPostgresSaver.from_conn_string(url) as second_saver:
        restarted = _supervisor(second_gateway, second_saver)
        approved = await restarted.resume_approval(
            request_id=str(uuid4()),
            thread_id=thread_id,
            auth=cfo,
            decision=ApprovalDecision.APPROVE,
            comment="Approved after simulated process restart",
        )
        await second_saver.adelete_thread(thread_id)
    if approved.status.value != "approved":
        raise AssertionError("restarted workflow did not resume to approval")
    if second_gateway.call_count:
        raise AssertionError("resume unexpectedly called the LLM")

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "checkpoint_backend": "neon_postgres",
        "application_pool_startup": "passed",
        "first_connection_closed_before_resume": True,
        "pending_status_before_restart": pending.status.value,
        "status_after_restart": approved.status.value,
        "approver_role": approved.approval["decided_by_role"],
        "submission_allowed": approved.action_draft["submission_allowed"],
        "llm_calls_before_restart": first_gateway.call_count,
        "llm_calls_after_restart": second_gateway.call_count,
        "verification_thread_cleaned_up": True,
    }


def main() -> None:
    if sys.platform == "win32":
        report = asyncio.run(verify(), loop_factory=asyncio.SelectorEventLoop)
    else:
        report = asyncio.run(verify())
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Pending approval restored after restart: passed")
    print("LLM calls during resume: 0")
    print("Verification checkpoint cleaned up: yes")


if __name__ == "__main__":
    main()

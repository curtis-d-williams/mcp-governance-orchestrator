# SPDX-License-Identifier: MIT
"""Regression tests for capability effectiveness ledger helpers."""

from src.mcp_governance_orchestrator.capability_effectiveness_ledger import (
    record_normalized_synthesis_event,
)


def test_record_normalized_synthesis_event_records_similarity_fields():
    ledger = {"capabilities": {}}

    result = record_normalized_synthesis_event(
        ledger,
        {
            "capability": "github_repository_management",
            "artifact_kind": "mcp_server",
            "status": "ok",
            "source": "planner_request",
            "used_evolution": True,
            "similarity_score": 0.61,
            "previous_similarity_score": 0.37,
            "similarity_delta": 0.24,
        },
    )

    assert result == {
        "capabilities": {
            "github_repository_management": {
                "artifact_kind": "mcp_server",
                "failed_syntheses": 0,
                "successful_syntheses": 1,
                "successful_evolved_syntheses": 1,
                "total_syntheses": 1,
                "last_synthesis_source": "planner_request",
                "last_synthesis_status": "ok",
                "last_synthesis_used_evolution": True,
                "similarity_score": 0.61,
                "previous_similarity_score": 0.37,
                "similarity_delta": 0.24,
            }
        }
    }


def test_record_normalized_synthesis_event_omits_similarity_fields_when_absent():
    ledger = {"capabilities": {}}

    result = record_normalized_synthesis_event(
        ledger,
        {
            "capability": "snowflake_data_access",
            "artifact_kind": "data_connector",
            "status": "ok",
            "source": "portfolio_gap",
        },
    )

    assert result == {
        "capabilities": {
            "snowflake_data_access": {
                "artifact_kind": "data_connector",
                "failed_syntheses": 0,
                "successful_syntheses": 1,
                "successful_evolved_syntheses": 0,
                "total_syntheses": 1,
                "last_synthesis_source": "portfolio_gap",
                "last_synthesis_status": "ok",
                "last_synthesis_used_evolution": False,
            }
        }
    }

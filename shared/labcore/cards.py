"""Agent cards in the A2A card shape (plain JSON, no a2a-sdk dependency). Each lab declares one in
`<package>/card.py`; `scripts/export_agent_cards.py` renders them into control-plane/agent-cards/."""

from __future__ import annotations

from typing import Any

OWNER_URL = "https://github.com/jagadishmazure-jpg"


def agent_card(
    *,
    agent_id: str,
    name: str,
    description: str,
    skills: list[dict[str, Any]],
    owner: str,
    model_deployment: str,
    data_zone: str,
    side_effect_class: str,
    denied_tools: list[str],
    eval_gate: list[str],
    human_review: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "version": "0.1.0",
        "provider": {"organization": "Azure agent labs (demo)", "url": OWNER_URL},
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json"],
        "capabilities": {
            "streaming": False,
            "extensions": [
                {
                    "uri": "urn:azure-agent-labs:control-plane:v1",
                    "description": "Owner, deployment zone, side effects, deny list, eval gate, reviewer",
                    "params": {
                        "agent_id": agent_id,
                        "owner": owner,
                        "stage": "lab",
                        "deployed": False,
                        "model_deployment": model_deployment,
                        "data_zone": data_zone,
                        "side_effect_class": side_effect_class,
                        "denied_tools": sorted(denied_tools),
                        "eval_gate": eval_gate,
                        "human_review": human_review,
                    },
                }
            ],
        },
        "skills": [
            {
                "id": s["id"],
                "name": s["name"],
                "description": s["description"],
                "inputModes": ["application/json"],
                "outputModes": ["application/json"],
                "tags": s.get("tags", []),
            }
            for s in skills
        ],
        "supportedInterfaces": [
            {"protocolBinding": "JSONRPC", "protocolVersion": "1.0", "url": f"http://{agent_id}.local/a2a"}
        ],
    }

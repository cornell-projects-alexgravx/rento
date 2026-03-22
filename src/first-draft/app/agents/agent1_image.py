"""Agent 1: Image Analysis.

Analyzes apartment images via Claude vision and stores style labels
back on the Apartment row. Runs as a background task or scheduled batch.
"""

import json
import uuid
from datetime import datetime
from typing import Optional

from langgraph.graph import END, START, StateGraph
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import TypedDict

from app.agents.shared.claude_client import MODEL, get_claude_client
from app.models.agent_logs import Agent1Log
from app.models.apartment import Apartment


class Agent1State(TypedDict):
    apartment_id: str
    images: list[str]
    labels: list[str]
    description: str
    error: Optional[str]


def build_agent1_graph(session: AsyncSession):
    """Build and compile an Agent 1 LangGraph. Session injected via closure.

    Args:
        session: An open AsyncSession. The caller is responsible for its lifecycle.

    Returns:
        A compiled LangGraph graph ready for ``ainvoke``.
    """

    async def fetch_apartment(state: Agent1State) -> dict:
        apt = await session.get(Apartment, state["apartment_id"])
        if not apt or not apt.images:
            return {
                "error": (
                    f"Apartment {state['apartment_id']} not found or has no images"
                ),
                "images": [],
            }
        return {"images": list(apt.images)}

    async def call_claude_vision(state: Agent1State) -> dict:
        if state.get("error"):
            return {}
        client = get_claude_client()
        content: list[dict] = []
        for url in (state.get("images") or [])[:5]:
            content.append({"type": "image", "source": {"type": "url", "url": url}})
        content.append(
            {
                "type": "text",
                "text": (
                    "Analyze these apartment photos. Return ONLY valid JSON with exactly two keys:\n"
                    '- "labels": list of up to 10 short style/vibe strings '
                    '(e.g. ["bright", "minimalist", "hardwood-floors"])\n'
                    '- "description": one paragraph describing the apartment style and feel.\n'
                    "No markdown, no code blocks, just raw JSON."
                ),
            }
        )
        try:
            response = await client.messages.create(
                model=MODEL,
                max_tokens=512,
                messages=[{"role": "user", "content": content}],
            )
            raw = response.content[0].text.strip()
            parsed = json.loads(raw)
            return {
                "labels": parsed.get("labels", []),
                "description": parsed.get("description", ""),
            }
        except Exception as exc:
            return {"error": str(exc)}

    async def persist_results(state: Agent1State) -> dict:
        apt = await session.get(Apartment, state["apartment_id"])
        if not apt:
            return {}

        if not state.get("error"):
            apt.image_labels = state.get("labels", [])

        result_str = json.dumps(
            {"status": "error", "error": state.get("error")}
            if state.get("error")
            else {
                "status": "success",
                "labels_count": len(state.get("labels", [])),
            }
        )
        log = Agent1Log(
            id=str(uuid.uuid4()),
            apartment_id=state["apartment_id"],
            source="agent1_image",
            timestamp=datetime.utcnow(),
            content=f"Analyzed {len(state.get('images', []))} images",
            result=result_str,
        )
        session.add(log)
        await session.commit()
        return {}

    g: StateGraph = StateGraph(Agent1State)
    g.add_node("fetch_apartment", fetch_apartment)
    g.add_node("call_claude_vision", call_claude_vision)
    g.add_node("persist_results", persist_results)
    g.add_edge(START, "fetch_apartment")
    g.add_edge("fetch_apartment", "call_claude_vision")
    g.add_edge("call_claude_vision", "persist_results")
    g.add_edge("persist_results", END)
    return g.compile()


async def run_agent1(apartment_id: str) -> None:
    """Entry point for background task execution. Creates its own DB session.

    Args:
        apartment_id: Primary key of the Apartment to analyze.
    """
    from app.database import async_session_factory

    async with async_session_factory() as session:
        graph = build_agent1_graph(session)
        initial_state: Agent1State = {
            "apartment_id": apartment_id,
            "images": [],
            "labels": [],
            "description": "",
            "error": None,
        }
        await graph.ainvoke(initial_state)


async def run_agent1_batch() -> int:
    """Scheduled batch: find all apartments with empty image_labels and analyze them.

    Called by APScheduler every 2 hours.

    Returns:
        Number of apartments processed.
    """
    from app.database import async_session_factory

    async with async_session_factory() as session:
        result = await session.execute(
            select(Apartment).where(
                or_(
                    Apartment.image_labels == None,  # noqa: E711
                    Apartment.image_labels == [],
                )
            )
        )
        apartments = result.scalars().all()

    for apt in apartments:
        await run_agent1(apt.id)

    return len(apartments)

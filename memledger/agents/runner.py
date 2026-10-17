"""The agent loop: the model asks for tools, we run them, until it answers."""
from dataclasses import dataclass, field

from .roles import TOOLSETS, system_prompt
from .tools import AgentContext, call_tool, tool_schemas

MAX_STEPS = 8


@dataclass
class AgentRun:
    agent: str
    text: str
    tool_calls: list = field(default_factory=list)
    steps: int = 0
    stopped: str = "answered"      # answered | max_steps


def run_agent(ctx: AgentContext, llm, task: str, max_steps: int = MAX_STEPS) -> AgentRun:
    """Run one agent on one task with a fresh chat. Nothing carries over
    between runs except what is in the graph."""
    names = TOOLSETS[ctx.agent]
    session = llm.start(system_prompt(ctx.agent, ctx.subject), tool_schemas(names))
    reply = session.send(task)
    steps = 1
    while reply.calls:
        if steps >= max_steps:
            return AgentRun(ctx.agent, reply.text or "", ctx.log, steps, "max_steps")
        results = []
        for c in reply.calls:
            if c["name"] in names:
                result = call_tool(ctx, c["name"], c["args"])
            else:
                result = {"error": f"tool {c['name']} is not available to {ctx.agent}"}
                ctx.log.append({"tool": c["name"], "args": c["args"], "result": result})
            results.append((c["name"], result))
        reply = session.send_tool_results(results)
        steps += 1
    return AgentRun(ctx.agent, reply.text or "", ctx.log, steps, "answered")

"""Chat models with tool calling, behind one small interface.

    session = llm.start(system_prompt, tool_schemas)
    reply = session.send(user_text)              # first turn
    reply = session.send_tool_results(results)   # after reply.calls
    reply.text / reply.calls -> [{"name", "args"}]
"""
from dataclasses import dataclass, field

from .. import config


@dataclass
class Reply:
    text: str | None = None
    calls: list = field(default_factory=list)


class GeminiChat:
    """Gemini function calling with automatic execution disabled, so our loop
    runs the tools. The model's own response content is appended verbatim to
    the history, which keeps any thought signatures newer models require."""

    def __init__(self, model: str | None = None, api_key: str | None = None, client=None):
        self.model = model or config.GEMINI_MODEL
        if client is None:
            from google import genai
            client = genai.Client(api_key=api_key or config.GEMINI_API_KEY)
        self.client = client

    def start(self, system: str, tools: list[dict]):
        return _GeminiSession(self, system, tools)


class _GeminiSession:
    def __init__(self, chat: GeminiChat, system: str, tools: list[dict]):
        from google.genai import types
        self.t = types
        self.chat = chat
        self.contents = []
        decls = [types.FunctionDeclaration(name=s["name"], description=s["description"],
                                           parameters_json_schema=s["parameters"]) for s in tools]
        self.config = types.GenerateContentConfig(
            system_instruction=system,
            tools=[types.Tool(function_declarations=decls)] if decls else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=0,
        )

    def _generate(self) -> Reply:
        resp = self.chat.client.models.generate_content(
            model=self.chat.model, contents=self.contents, config=self.config)
        content = resp.candidates[0].content
        self.contents.append(content)
        calls = [{"name": c.name, "args": dict(c.args or {})} for c in (resp.function_calls or [])]
        text = None if calls else "".join(p.text or "" for p in (content.parts or []) if p.text)
        return Reply(text=text, calls=calls)

    def send(self, text: str) -> Reply:
        self.contents.append(self.t.Content(role="user", parts=[self.t.Part.from_text(text=text)]))
        return self._generate()

    def send_tool_results(self, results: list[tuple[str, dict]]) -> Reply:
        parts = [self.t.Part.from_function_response(name=n, response={"result": r}) for n, r in results]
        self.contents.append(self.t.Content(role="user", parts=parts))
        return self._generate()


class ScriptedChat:
    """For tests and offline demos. `script` is a list of steps; each step is a
    Reply or a function (last_results) -> Reply, where last_results is the list
    of (tool name, result) pairs from the previous step."""

    def __init__(self, script):
        self.script = list(script)
        self.sessions = []

    def start(self, system, tools):
        s = _ScriptedSession(self.script, system, tools)
        self.sessions.append(s)
        return s


class _ScriptedSession:
    def __init__(self, script, system, tools):
        self.script, self.system, self.tools = script, system, tools
        self.inputs = []

    def _next(self, last):
        step = self.script.pop(0)
        return step(last) if callable(step) else step

    def send(self, text):
        self.inputs.append(text)
        return self._next([])

    def send_tool_results(self, results):
        self.inputs.append(results)
        return self._next(results)

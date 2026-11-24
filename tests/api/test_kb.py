"""Knowledge base: every scheme's clauses, and the all-scheme grounded chat."""
from fastapi.testclient import TestClient

from api.deps import get_llm
from api.main import app


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply

    def complete(self, system, user, tier=None, **kwargs):
        return self.reply


def test_knowledge_lists_every_served_scheme_with_its_clauses():
    client = TestClient(app)
    served = {s["id"] for s in client.get("/schemes").json()["schemes"]}
    kb = client.get("/kb").json()["schemes"]
    assert {s["id"] for s in kb} == served
    assert all(s["clauses"] and all(c["quote"] for c in s["clauses"]) for s in kb)


def test_kb_ask_needs_a_question():
    assert TestClient(app).post("/kb/ask", json={"question": ""}).status_code == 422

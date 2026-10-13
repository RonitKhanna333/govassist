"""The household graph: linking, privacy, and what it may suggest.

The failure modes worth testing are mostly about consent and leakage --
someone added to a family without agreeing, one member's answers visible to
another, a member id from another household that still resolves -- plus
the one place the graph touches a verdict: the "one person per family"
rule, where the clause, not this code, defines who counts as family.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from api.auth import router as auth_router_mod
from api.db import Base, get_engine, get_session_factory
from api.family import derive
from api.main import app

SECRET = "x" * 48
PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)


@pytest.fixture
def client():
    engine = get_engine("sqlite:///:memory:")
    from api.auth import models  # noqa: F401
    from api.family import models as family_models  # noqa: F401
    Base.metadata.create_all(engine)
    sessions = get_session_factory(engine)
    app.dependency_overrides[auth_router_mod.get_sessions] = lambda: sessions
    yield TestClient(app)
    app.dependency_overrides.pop(auth_router_mod.get_sessions, None)


def _account(client, email: str) -> dict:
    token = client.post("/auth/register", json={"email": email, "password": PASSWORD}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _family(client, headers, my_name="Ramesh") -> dict:
    response = client.post("/family", json={"my_name": my_name}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _add(client, headers, name, relation=None, **extra) -> dict:
    body = {"name": name, **extra}
    if relation:
        body["relation"] = relation
    response = client.post("/family/members", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _id(graph, name) -> int:
    return next(m["id"] for m in graph["members"] if m["name"] == name)


# -- building the tree ------------------------------------------------------


def test_creating_a_family_makes_you_its_first_member(client):
    me = _account(client, "a@x.in")
    graph = _family(client, me)
    assert graph["members"] == [{
        "id": graph["me"], "name": "Ramesh", "birth_year": None, "relation": "self",
        "has_account": True, "shares_profile": False, "benefits": [],
    }]


def test_relations_are_derived_from_two_kinds_of_edge(client):
    me = _account(client, "a@x.in")
    _family(client, me)
    _add(client, me, "Sita", "spouse")
    _add(client, me, "Mohan", "parent")
    graph = _add(client, me, "Asha", "child")
    graph = client.post("/family/relations", headers=me, json={
        "from_member": _id(graph, "Mohan"), "predicate": "parent_of",
        "to_member": _add(client, me, "Suresh")["members"][-1]["id"],
    }).json()
    relation = {m["name"]: m["relation"] for m in graph["members"]}
    assert relation == {"Ramesh": "self", "Sita": "spouse", "Mohan": "parent",
                        "Asha": "child", "Suresh": "sibling"}
    # Only parent_of and spouse_of are ever stored.
    assert {r["predicate"] for r in graph["relations"]} <= {"parent_of", "spouse_of"}


def test_nobody_can_be_their_own_ancestor(client):
    me = _account(client, "a@x.in")
    _family(client, me)
    graph = _add(client, me, "Asha", "child")
    response = client.post("/family/relations", headers=me, json={
        "from_member": _id(graph, "Asha"), "predicate": "parent_of",
        "to_member": graph["me"]})
    assert response.status_code == 422


def test_a_third_parent_is_refused(client):
    me = _account(client, "a@x.in")
    _family(client, me)
    _add(client, me, "Mohan", "parent")
    graph = _add(client, me, "Kamla", "parent")
    graph = _add(client, me, "Someone")
    response = client.post("/family/relations", headers=me, json={
        "from_member": _id(graph, "Someone"), "predicate": "parent_of",
        "to_member": graph["me"]})
    assert response.status_code == 422


def test_one_household_per_account(client):
    me = _account(client, "a@x.in")
    _family(client, me)
    assert client.post("/family", json={"my_name": "again"}, headers=me).status_code == 409


def test_family_needs_sign_in(client):
    assert client.get("/family").status_code == 401


# -- consent: joining -------------------------------------------------------


def test_a_relative_joins_only_by_redeeming_a_code_themselves(client):
    me = _account(client, "a@x.in")
    _family(client, me)
    graph = _add(client, me, "Sita", "spouse")
    code = client.post("/family/invites", json={"member_id": _id(graph, "Sita")},
                       headers=me).json()["code"]

    sita = _account(client, "s@x.in")
    joined = client.post("/family/join", json={"code": code}, headers=sita).json()
    assert joined["me"] == _id(graph, "Sita")
    assert {m["name"]: m["relation"] for m in joined["members"]}["Ramesh"] == "spouse"


def test_invite_codes_are_single_use(client):
    me = _account(client, "a@x.in")
    _family(client, me)
    graph = _add(client, me, "Sita", "spouse")
    code = client.post("/family/invites", json={"member_id": _id(graph, "Sita")},
                       headers=me).json()["code"]
    assert client.post("/family/join", json={"code": code},
                       headers=_account(client, "s@x.in")).status_code == 200
    assert client.post("/family/join", json={"code": code},
                       headers=_account(client, "t@x.in")).status_code == 404


def test_a_wrong_code_and_a_used_code_look_the_same(client):
    """Don't tell someone guessing codes which ones exist."""
    other = _account(client, "z@x.in")
    response = client.post("/family/join", json={"code": "DEADBEEF"}, headers=other)
    assert response.status_code == 404
    assert response.json()["detail"] == "That code isn't valid"


def test_only_a_hash_of_the_code_is_stored(client):
    me = _account(client, "a@x.in")
    _family(client, me)
    graph = _add(client, me, "Sita", "spouse")
    code = client.post("/family/invites", json={"member_id": _id(graph, "Sita")},
                       headers=me).json()["code"]
    sessions = app.dependency_overrides[auth_router_mod.get_sessions]()
    from sqlalchemy import select
    from api.family.models import Invite
    with sessions() as session:
        stored = session.scalars(select(Invite)).one()
    assert code not in stored.code_hash


# -- isolation between households -------------------------------------------


def test_another_familys_member_ids_do_not_resolve(client):
    a = _account(client, "a@x.in")
    _family(client, a)
    graph_a = _add(client, a, "Sita", "spouse")
    b = _account(client, "b@x.in")
    _family(client, b, "Other")
    sita = _id(graph_a, "Sita")
    for path, body in (("/family/invites", {"member_id": sita}),
                       ("/family/benefits", {"member_id": sita, "scheme": "pmfme"})):
        assert client.post(path, json=body, headers=b).status_code == 404


def test_another_familys_graph_is_never_returned(client):
    a = _account(client, "a@x.in")
    _family(client, a)
    _add(client, a, "Sita", "spouse")
    b = _account(client, "b@x.in")
    graph_b = _family(client, b, "Other")
    assert [m["name"] for m in graph_b["members"]] == ["Other"]


# -- privacy of answers -----------------------------------------------------


def _save_profile(client, headers, profile):
    assert client.put("/auth/profile", json={"profile": profile},
                      headers=headers).status_code == 200


def test_a_relatives_answers_are_private_until_they_share(client):
    me = _account(client, "a@x.in")
    _family(client, me)
    graph = _add(client, me, "Sita", "spouse")
    code = client.post("/family/invites", json={"member_id": _id(graph, "Sita")},
                       headers=me).json()["code"]
    sita = _account(client, "s@x.in")
    client.post("/family/join", json={"code": code}, headers=sita)
    _save_profile(client, sita, {"age": 30, "has_bank_or_post_office_account": True,
                                 "consents_to_auto_debit": True})

    view = {m["name"]: m for m in client.get("/family/eligibility", headers=me).json()["members"]}
    assert view["Sita"]["private"] is True
    assert view["Sita"]["schemes"] == {}

    client.put("/family/sharing", json={"share": True}, headers=sita)
    view = {m["name"]: m for m in client.get("/family/eligibility", headers=me).json()["members"]}
    assert view["Sita"]["private"] is False
    assert view["Sita"]["schemes"]["pmsby"] == "ELIGIBLE"


def test_a_record_without_an_account_is_visible_to_the_family(client):
    me = _account(client, "a@x.in")
    _family(client, me)
    _add(client, me, "Mohan", "parent",
         profile={"age": 65, "has_bank_or_post_office_account": True,
                  "consents_to_auto_debit": True})
    view = {m["name"]: m for m in client.get("/family/eligibility", headers=me).json()["members"]}
    assert view["Mohan"]["schemes"]["pmsby"] == "ELIGIBLE"
    assert view["Mohan"]["schemes"]["apy"] == "NOT_ELIGIBLE"   # over 40


def test_a_relatives_record_holds_only_known_validated_answers(client):
    """No free-form fields on someone else's node -- nothing that could hold
    an ID number or a note about them."""
    me = _account(client, "a@x.in")
    _family(client, me)
    graph = _add(client, me, "Mohan", "parent",
                 profile={"age": 65, "aadhaar": "1234 5678 9012"})
    assert graph  # the unknown key was dropped, not stored
    bad = client.post("/family/members", headers=me,
                      json={"name": "X", "profile": {"age": -4}})
    assert bad.status_code == 422


def test_the_graph_never_exposes_account_details(client):
    me = _account(client, "a@x.in")
    graph = _family(client, me)
    text = json.dumps(graph)
    assert "a@x.in" not in text
    assert "user_id" not in text and "password" not in text


def test_joining_clears_the_record_entered_on_your_behalf(client):
    me = _account(client, "a@x.in")
    _family(client, me)
    graph = _add(client, me, "Sita", "spouse", profile={"age": 30})
    code = client.post("/family/invites", json={"member_id": _id(graph, "Sita")},
                       headers=me).json()["code"]
    client.post("/family/join", json={"code": code}, headers=_account(client, "s@x.in"))
    view = {m["name"]: m for m in client.get("/family/eligibility", headers=me).json()["members"]}
    assert view["Sita"]["private"] is True


# -- benefits and the one-person-per-family rule ----------------------------


def test_a_spouse_who_received_pmfme_is_suggested_with_its_source(client):
    me = _account(client, "a@x.in")
    _family(client, me)
    graph = _add(client, me, "Sita", "spouse")
    client.post("/family/benefits", json={"member_id": _id(graph, "Sita"), "scheme": "pmfme"},
                headers=me)
    body = client.get("/family/suggestions?scheme=pmfme", headers=me).json()
    assert body["suggestions"] == [{
        "attribute": "family_member_already_received_assistance", "value": True,
        "clause": "individual-one-person-per-family",
        "because": [{"member_id": _id(graph, "Sita"), "name": "Sita",
                     "relation": "spouse", "scheme": "pmfme"}],
    }]


def test_a_parent_who_received_pmfme_is_not_family_for_that_rule(client):
    """The clause defines family as self, spouse and children. A parent is
    not in it, so a father's subsidy must not count against his son."""
    me = _account(client, "a@x.in")
    _family(client, me)
    graph = _add(client, me, "Mohan", "parent")
    client.post("/family/benefits", json={"member_id": _id(graph, "Mohan"), "scheme": "pmfme"},
                headers=me)
    assert client.get("/family/suggestions?scheme=pmfme",
                      headers=me).json()["suggestions"] == []


def test_a_benefit_for_a_different_scheme_suggests_nothing(client):
    me = _account(client, "a@x.in")
    _family(client, me)
    graph = _add(client, me, "Sita", "spouse")
    client.post("/family/benefits", json={"member_id": _id(graph, "Sita"), "scheme": "apy"},
                headers=me)
    assert client.get("/family/suggestions?scheme=pmfme",
                      headers=me).json()["suggestions"] == []


def test_suggestions_are_never_applied_to_a_verdict(client):
    """A suggestion is a reminder. The chat verdict still comes only from
    what the person answered."""
    me = _account(client, "a@x.in")
    _family(client, me)
    graph = _add(client, me, "Sita", "spouse")
    client.post("/family/benefits", json={"member_id": _id(graph, "Sita"), "scheme": "pmfme"},
                headers=me)
    chat = client.post("/chat", json={"scheme": "pmfme", "profile": {}}, headers=me).json()
    assert "family_member_already_received_assistance" not in chat["profile"]


def test_a_member_with_an_account_records_their_own_benefits(client):
    me = _account(client, "a@x.in")
    _family(client, me)
    graph = _add(client, me, "Sita", "spouse")
    code = client.post("/family/invites", json={"member_id": _id(graph, "Sita")},
                       headers=me).json()["code"]
    client.post("/family/join", json={"code": code}, headers=_account(client, "s@x.in"))
    response = client.post("/family/benefits", headers=me,
                           json={"member_id": _id(graph, "Sita"), "scheme": "pmfme"})
    assert response.status_code == 403


def test_unknown_schemes_are_refused(client):
    me = _account(client, "a@x.in")
    graph = _family(client, me)
    for scheme in ("../etc", "nope"):
        assert client.post("/family/benefits", headers=me,
                           json={"member_id": graph["me"], "scheme": scheme}).status_code == 404


def test_the_family_definition_still_matches_the_clause():
    """FAMILY_RULES encodes what a clause says. If the clause is edited,
    this table must be re-checked by a person -- this test makes that
    impossible to miss."""
    from api.rules.engine import load_clauses
    from parse_scheme import repo_root
    for scheme, rule in derive.FAMILY_RULES.items():
        clause = load_clauses(scheme, repo_root())[rule["clause"]]
        quote = " ".join(clause["quote"].split()).lower()
        assert "self" in quote and "spouse" in quote and "children" in quote
        assert rule["relations"] == {"spouse", "child"}


# -- leaving ----------------------------------------------------------------


def test_leaving_unlinks_you_and_keeps_the_tree(client):
    me = _account(client, "a@x.in")
    _family(client, me)
    graph = _add(client, me, "Sita", "spouse")
    code = client.post("/family/invites", json={"member_id": _id(graph, "Sita")},
                       headers=me).json()["code"]
    sita = _account(client, "s@x.in")
    client.post("/family/join", json={"code": code}, headers=sita)

    assert client.post("/family/leave", headers=sita).json() == {
        "left": True, "household_deleted": False}
    assert client.get("/family", headers=sita).status_code == 404
    members = {m["name"]: m for m in client.get("/family", headers=me).json()["members"]}
    assert members["Sita"]["has_account"] is False


def test_the_last_account_to_leave_deletes_the_household(client):
    me = _account(client, "a@x.in")
    _family(client, me)
    _add(client, me, "Asha", "child")
    assert client.post("/family/leave", headers=me).json()["household_deleted"] is True
    assert client.post("/family", json={"my_name": "Ramesh"}, headers=me).status_code == 200


# -- traversal, directly ----------------------------------------------------


class E:
    def __init__(self, a, p, b):
        self.from_member, self.predicate, self.to_member = a, p, b


def test_grandparents_and_grandchildren():
    edges = [E(1, "parent_of", 2), E(2, "parent_of", 3)]
    assert derive.relation_labels(3, edges) == {2: "parent", 1: "grandparent"}
    assert derive.relation_labels(1, edges) == {2: "child", 3: "grandchild"}


def test_a_spouse_is_never_also_labelled_a_sibling():
    edges = [E(1, "parent_of", 2), E(1, "parent_of", 3), E(2, "spouse_of", 3)]
    assert derive.relation_labels(2, edges)[3] == "spouse"

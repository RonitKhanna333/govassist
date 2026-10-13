"""Traversal over the household graph, and what it can suggest.

Relationship labels are derived, never stored: only `parent_of` and
`spouse_of` edges exist (see models.py), and child, sibling and grandparent
fall out of following them.

Which relatives count as "family" is NOT decided here. Each scheme's own
clause defines it, and FAMILY_RULES records which clause and which
relations -- so the definition is cited, and a test checks the clause still
says what this table assumes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from api.family.models import BenefitRecord, Member, Relation

# scheme -> the family-level attribute, which relatives the scheme's clause
# counts as family, and the clause that says so.
#
# PMFME, clause individual-one-person-per-family: 'The "family" for this
# purpose would include self, spouse and children'. Parents and siblings are
# deliberately absent -- the clause does not include them, so a father who
# received PMFME does not stop his adult son applying.
FAMILY_RULES: dict[str, dict] = {
    "pmfme": {
        "attribute": "family_member_already_received_assistance",
        "relations": {"spouse", "child"},
        "clause": "individual-one-person-per-family",
    },
}


def relation_labels(me: int, relations: list[Relation]) -> dict[int, str]:
    """member id -> how that member relates to `me`."""
    parents_of: dict[int, set[int]] = {}
    children_of: dict[int, set[int]] = {}
    spouses: dict[int, set[int]] = {}
    for edge in relations:
        if edge.predicate == "parent_of":
            children_of.setdefault(edge.from_member, set()).add(edge.to_member)
            parents_of.setdefault(edge.to_member, set()).add(edge.from_member)
        elif edge.predicate == "spouse_of":
            spouses.setdefault(edge.from_member, set()).add(edge.to_member)
            spouses.setdefault(edge.to_member, set()).add(edge.from_member)

    labels: dict[int, str] = {}

    def put(member: int, label: str) -> None:
        # Closest relationship wins: a spouse is never also a "sibling".
        if member != me and member not in labels:
            labels[member] = label

    for m in spouses.get(me, ()):
        put(m, "spouse")
    for m in children_of.get(me, ()):
        put(m, "child")
    for m in parents_of.get(me, ()):
        put(m, "parent")
    for parent in parents_of.get(me, ()):
        for sibling in children_of.get(parent, ()):
            put(sibling, "sibling")
        for grandparent in parents_of.get(parent, ()):
            put(grandparent, "grandparent")
    for child in children_of.get(me, ()):
        for grandchild in children_of.get(child, ()):
            put(grandchild, "grandchild")
    # In-laws: in a joint family the people under one roof are often related
    # by marriage, and "not linked" would be wrong for a father-in-law.
    for spouse in spouses.get(me, ()):
        for in_law in parents_of.get(spouse, ()):
            put(in_law, "parent_in_law")
    for child in children_of.get(me, ()):
        for in_law in spouses.get(child, ()):
            put(in_law, "child_in_law")

    # Anyone else reachable through the graph is family, just not one of the
    # named relationships. Only someone with no path at all is "not linked".
    neighbours: dict[int, set[int]] = {}
    for edge in relations:
        neighbours.setdefault(edge.from_member, set()).add(edge.to_member)
        neighbours.setdefault(edge.to_member, set()).add(edge.from_member)
    stack, seen = [me], {me}
    while stack:
        node = stack.pop()
        for other in neighbours.get(node, ()):
            if other not in seen:
                seen.add(other)
                stack.append(other)
                put(other, "relative")
    return labels


def would_create_cycle(parent: int, child: int, relations: list[Relation]) -> bool:
    """True if `parent` is already a descendant of `child` (or is `child`)."""
    if parent == child:
        return True
    children_of: dict[int, set[int]] = {}
    for edge in relations:
        if edge.predicate == "parent_of":
            children_of.setdefault(edge.from_member, set()).add(edge.to_member)
    stack, seen = [child], set()
    while stack:
        node = stack.pop()
        if node == parent:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(children_of.get(node, ()))
    return False


@dataclass
class Suggestion:
    """A fact from the family record, offered -- never applied."""
    attribute: str
    value: object
    clause: str
    because: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"attribute": self.attribute, "value": self.value,
                "clause": self.clause, "because": self.because}


def suggestions(scheme: str, me: int, members: list[Member],
                relations: list[Relation],
                benefits: list[BenefitRecord]) -> list[Suggestion]:
    rule = FAMILY_RULES.get(scheme)
    if rule is None:
        return []
    labels = relation_labels(me, relations)
    names = {m.id: m.name for m in members}
    because = [
        {"member_id": b.member_id, "name": names.get(b.member_id, ""),
         "relation": labels[b.member_id], "scheme": b.scheme}
        for b in benefits
        if b.scheme == scheme and labels.get(b.member_id) in rule["relations"]
    ]
    if not because:
        return []
    return [Suggestion(rule["attribute"], True, rule["clause"], because)]


def visible_profile(member: Member, viewer_user_id: int, user_profiles: dict[int, str]) -> dict | None:
    """The answers the viewer may see for this member, or None.

    Your own saved answers; another account holder's only if they chose to
    share; an account-less member's record (entered by the family).
    """
    if member.user_id is None:
        return _load(member.profile_json)
    if member.user_id == viewer_user_id or member.shares_profile:
        return _load(user_profiles.get(member.user_id, "{}"))
    return None


def _load(raw: str | None) -> dict:
    try:
        value = json.loads(raw or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}

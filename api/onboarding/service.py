"""Turning interview answers into a profile, a result, and a stored record."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from api.onboarding import interview
from api.onboarding.models import CallRecord
from api.rules.engine import decide
from api.rules.forms import OTHER, Field
from api.rules.spoken import parse_number, parse_yes_no
from api.rules.values import check_values, specs_for
from api.rules.engine import load_rules
from parse_scheme import repo_root


def fields(locale: str = "en") -> dict[str, Field]:
    out = {}
    for attr in interview.order():
        f = interview.field_for(attr, locale)
        if f is not None:
            out[attr] = f
    return out


def read_answers(heard: dict) -> tuple[dict, list[str]]:
    """Spoken answers -> values, for any scheme's question.

    Only what our deterministic parser reads is kept. "पता नहीं", a hedge
    or two different numbers stay out of the profile and are listed in
    `unparsed`, so the dashboard can ask again rather than guess.
    """
    known = fields()
    profile: dict = {}
    unparsed: list[str] = []
    for attribute, raw in (heard or {}).items():
        f = known.get(attribute)
        if f is None or raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        if f.kind == "number":
            number = raw if isinstance(raw, (int, float)) and not isinstance(raw, bool) \
                else parse_number(text)
            if number is None or number < 0:
                unparsed.append(attribute)
            else:
                profile[attribute] = number
            continue
        said_yes = raw if isinstance(raw, bool) else parse_yes_no(text)
        if said_yes is None:
            unparsed.append(attribute)
        elif f.kind == "choice":
            profile[attribute] = f.satisfied_by if said_yes else OTHER
        else:
            profile[attribute] = said_yes
    specs = {}
    for slug in interview.schemes():
        specs.update(specs_for(load_rules(slug, repo_root())))
    checked = check_values(specs, profile)
    unparsed.extend(e.attribute for e in checked.errors)
    return checked.values, unparsed


def coerce_answers(raw) -> dict:
    """The tool's `answers` may arrive as an object or as its JSON text."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return {}
    return raw if isinstance(raw, dict) else {}


def summary_text(profile: dict, locale: str = "hi") -> str:
    """What the agent reads out at the end of a call. Decided by `decide()`;
    the wording is fixed text, so no model can add a scheme or an amount."""
    from api.voice.script import scheme_name

    verdicts = interview.verdicts(profile)
    if locale == "hi-Latn":
        eligible = [scheme_name(s, "en") for s, v in verdicts.items() if v == "ELIGIBLE"]
        missing = [scheme_name(s, "en") for s, v in verdicts.items() if v == "INSUFFICIENT_INFO"]
        parts = ["Aapke jawaabon ke hisaab se aap in schemes ke liye eligible lagte hain: "
                 + ", ".join(eligible) + "." if eligible else
                 "Aapke jawaabon se abhi kisi scheme ki eligibility pakki nahi ho paayi."]
        if missing:
            parts.append("In schemes ke liye kuch jawaab abhi baaki hain: " + ", ".join(missing) + ".")
        parts.append("Yeh sirf jaankaari hai, sarkari faisla nahi. Zaroori documents ki list aapke dashboard par hai.")
        return " ".join(parts)
    eligible = [scheme_name(s, locale) for s, v in verdicts.items() if v == "ELIGIBLE"]
    open_ = [scheme_name(s, locale) for s, v in verdicts.items() if v == "INSUFFICIENT_INFO"]
    hi = locale == "hi"
    parts = []
    if eligible:
        parts.append(("आपके जवाबों के हिसाब से आप इन योजनाओं के लिए पात्र लगते हैं: "
                      if hi else "From your answers, you appear eligible for: ")
                     + ", ".join(eligible) + ("।" if hi else "."))
    else:
        parts.append("आपके जवाबों के हिसाब से अभी किसी योजना के लिए पात्रता पक्की नहीं हो पाई।"
                     if hi else "From your answers, no scheme could be confirmed yet.")
    if open_:
        parts.append(("इनके लिए कुछ जवाब अभी बाकी हैं: " if hi
                      else "Some answers are still needed for: ") + ", ".join(open_)
                     + ("।" if hi else "."))
    parts.append("यह सिर्फ़ जानकारी है, सरकारी फ़ैसला नहीं। ज़रूरी काग़ज़ों की सूची आपके "
                 "डैशबोर्ड पर है।" if hi else
                 "This is guidance, not a government decision. The documents you need "
                 "are listed on your dashboard.")
    return " ".join(parts)


def transcript_lines(transcripts) -> list[dict]:
    out = []
    for t in transcripts or []:
        if isinstance(t, dict) and t.get("text") and t.get("user") in ("user", "assistant"):
            out.append({"who": "caller" if t["user"] == "user" else "agent",
                        "text": str(t["text"])})
    return out


def merge_profile(stored_json: str | None, new_values: dict) -> str:
    """Latest answers win, attribute by attribute; nothing is ever erased by
    a call that simply didn't cover it."""
    try:
        current = json.loads(stored_json or "{}")
    except ValueError:
        current = {}
    if not isinstance(current, dict):
        current = {}
    current.update(new_values)
    return json.dumps(current)


def complete_record(record: CallRecord, status: str, transcripts, heard: dict,
                    answers: dict) -> None:
    record.status = status
    record.transcript_json = json.dumps(transcript_lines(transcripts), ensure_ascii=False)
    record.heard_json = json.dumps(heard or {}, ensure_ascii=False)
    record.answers_json = json.dumps(answers or {}, ensure_ascii=False)
    record.completed_at = datetime.now(timezone.utc)


def evaluate(profile: dict) -> dict[str, object]:
    return {s: decide(s, profile) for s in interview.schemes()}

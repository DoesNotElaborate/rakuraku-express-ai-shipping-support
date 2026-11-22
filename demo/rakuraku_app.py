"""Local, synthetic-data-only RakuRaku policy retrieval demo."""
from __future__ import annotations

import json
import math
import os
import re
import urllib.request
from urllib.parse import urlparse
from collections import Counter
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
PDF = HERE / "RakuRaku_Express_Shipping_Policy.pdf"
if not PDF.exists():
    PDF = Path(r"C:\Users\phony\Desktop\RakuRaku_Express_Shipping_Policy.pdf")
prompt_path = HERE / "RakuRaku_CREATE_system_prompt.md"
if not prompt_path.exists():
    prompt_path = ROOT / "outputs" / "RakuRaku_CREATE_system_prompt.md"
PROMPT = prompt_path.read_text(encoding="utf-8")
RULES = {
    "3.1": "A standard shipment must arrive within 2 business days after pickup.",
    "3.2": "An expedited shipment must arrive within 1 business day after pickup.",
    "3.3": "An international shipment must arrive within 7 business days after pickup unless the order confirmation lists a different commitment.",
    "3.4": "A shipment is considered delivered only when the carrier scan includes a delivery date and destination scan. A customer statement without a carrier scan is not sufficient by itself.",
    "4.1": "Written notice must be received within 5 business days after delivery.",
    "4.2": "A weather exception requires official carrier documentation or a government weather alert attached within 3 business days after the notice is opened.",
    "4.3": "If a required date, invoice amount, or carrier record is missing, mark the case Evidence incomplete and request the missing information. Do not assume a value.",
    "5.1": "For a qualifying late standard or expedited delivery, the maximum standard credit equals the transportation charge on the invoice.",
    "5.2": "Frontline employees may approve a refund or credit up to $500 per shipment.",
    "5.3": "Any requested refund above $500, any credit above the transportation charge, or any exception requires Customer Operations Manager approval before being promised.",
    "5.4": "A weather delay does not qualify for the standard credit unless the required official documentation is attached and the manager confirms that the exception does not apply.",
    "5.5": "A shipment delayed because of an address entered incorrectly by the customer is not eligible for a late delivery credit.",
    "6.1": "A case involving a refund request above $500 must be escalated to a manager within 4 business hours.",
    "6.2": "A case involving a possible legal claim, bodily injury, threatened litigation, or suspected fraud must be escalated immediately and must not receive a substantive promise from the AI assistant.",
    "6.3": "If the policy does not clearly answer the customer question, state that the issue requires review. Do not invent a deadline, credit, exception, or contract term.",
    "7": "Every reviewed dispute must contain the shipment number, customer request, relevant policy sections, verified dates, transportation charge, exception evidence, proposed response, reviewer role, and final approval status. The AI assistant may draft a response and organize the case record, but it may not send an external message, approve a refund, or change a ticket status without human approval.",
    "8": "Confirm shipment and service; verify carrier dates; calculate business days; check notice; review exceptions; calculate permitted credit; draft cited response; obtain human approval before sending or changing a record.",
    "10": "The AI assistant may retrieve policy sections, summarize supplied facts, calculate dates when all inputs are present, identify missing evidence, and draft a proposed customer response. It must cite the policy section used and state Not established by this policy when the answer is unavailable. It must not guess, create a new policy rule, approve a payment, send an external message, alter a ticket, or treat a customer claim as verified without supporting records.",
}

def validate_source():
    text = " ".join(p.extract_text() for p in PdfReader(str(PDF)).pages)
    for key, value in RULES.items():
        if key in {"7", "8", "10"}:
            continue
        if f"Rule {key}:" not in text:
            raise RuntimeError(f"Policy source missing Rule {key}")

def tokens(s):
    return re.findall(r"[a-z0-9]+", s.lower())

def retrieve(query, limit=5):
    q = Counter(tokens(query))
    docs = [(key, Counter(tokens(value))) for key, value in RULES.items()]
    n = len(docs)
    scores = []
    for key, counts in docs:
        length = sum(counts.values())
        score = 0.0
        for term, count in q.items():
            if term not in counts:
                continue
            df = sum(1 for _, doc in docs if term in doc)
            idf = math.log(1 + (n - df + .5) / (df + .5))
            tf = counts[term] * 2.2 / (counts[term] + 1.2 * (.25 + .75 * length / 39))
            score += idf * tf * count
        if re.search(rf"\b(?:rule|section)\s*{re.escape(key)}\b", query, re.I):
            score += 12
        scores.append((score, key, RULES[key]))
    return [{"section": key, "text": value, "score": round(score, 2)} for score, key, value in sorted(scores, reverse=True)[:limit] if score > 0]

def business_days(start, end, holidays=()):
    if end < start:
        raise ValueError("Delivery precedes pickup")
    holiday_set = set(holidays)
    day = start
    result = 0
    while day < end:
        day += timedelta(days=1)
        if day.weekday() < 5 and day not in holiday_set:
            result += 1
    return result

def local_answer(case, passages):
    """Auditable deterministic fallback; not represented as LLM inference."""
    service = case.get("service", "")
    pickup, delivery, notice = (case.get(k) for k in ("pickup", "delivery", "notice"))
    charge = case.get("charge")
    if case.get("legal_or_fraud"):
        return "Draft — human review required. Escalate immediately without a substantive promise (Rule 6.2)."
    requested = case.get("requested_refund")
    high_request = requested is not None and float(requested) > 500
    escalation = " A refund request above $500 requires manager approval before any promise and escalation within 4 business hours (Rules 5.3 and 6.1)." if high_request else ""
    try:
        invalid = []
        if pickup and delivery and date.fromisoformat(delivery) < date.fromisoformat(pickup):
            invalid.append("delivery date precedes pickup")
        if charge is not None and float(charge) < 0:
            invalid.append("transportation charge is negative")
        if invalid:
            return "Draft — human review required. Status: Evidence incomplete. Invalid inputs: " + "; ".join(invalid) + ". Request corrected carrier records and invoice. Do not calculate a credit (Rules 3.4 and 4.3)." + escalation
    except (ValueError, TypeError):
        return "Draft — human review required. Status: Evidence incomplete. Request valid dates and invoice charge before calculation (Rule 4.3)." + escalation
    if not case.get("carrier_scan") or not pickup or not delivery or charge is None:
        return "Draft — human review required. Status: Evidence incomplete. Request verified carrier pickup and destination delivery scans, dates, and invoice transportation charge (Rules 3.4 and 4.3). No credit can be determined." + escalation
    try:
        p, d = date.fromisoformat(pickup), date.fromisoformat(delivery)
        days = business_days(p, d, [date.fromisoformat(x) for x in case.get("holidays", [])])
        amount = float(charge)
        if amount < 0:
            raise ValueError("Negative charge")
    except (ValueError, TypeError):
        return "Draft — human review required. Status: Evidence incomplete. Dates or transportation charge are invalid; request corrected evidence (Rule 4.3)."
    commitment = {"standard": (2, "3.1"), "expedited": (1, "3.2"), "international": (7, "3.3")}.get(service)
    if not commitment:
        return "Draft — human review required. Not established by this policy: service type is missing or unrecognized. Request service type (Section 8, Step 1; Rule 6.3)."
    if service == "international" and not case.get("order_confirmation"):
        return "Draft — human review required. Status: Evidence incomplete. Request the international order confirmation because it may specify a different commitment (Rule 3.3). A standard international credit amount is not established by Rule 5.1."
    if not case.get("holiday_calendar_verified"):
        return "Draft — human review required. Status: Evidence incomplete. Verify the company holiday calendar before final business-day calculation (Section 2; Section 8, Step 3)."
    if case.get("wrong_address"):
        return "Draft — human review required. Customer-entered incorrect address makes a late delivery credit ineligible (Rule 5.5). Human verification required (Section 7)."
    if case.get("weather"):
        return "Draft — human review required. Weather exception needs official evidence and manager review; no automatic credit determination (Rules 4.2 and 5.4)."
    if not notice:
        return "Draft — human review required. Status: Evidence incomplete. Request written notice date to check Rule 4.1 (Rule 4.3)."
    try:
        notice_days = business_days(d, date.fromisoformat(notice), [date.fromisoformat(x) for x in case.get("holidays", [])])
    except ValueError:
        return "Draft — human review required. Status: Evidence incomplete. Correct the notice date (Rule 4.3)."
    if notice_days > 5:
        return f"Draft — human review required. Written notice arrived {notice_days} business days after delivery, outside the five-business-day window (Rule 4.1). Human review required (Section 7)."
    if days <= commitment[0]:
        return f"Draft — human review required. Verified delivery took {days} business day(s), within the {commitment[0]}-business-day {service} commitment (Rule {commitment[1]}). No late delivery credit is indicated. Human review required (Section 7)."
    if service == "international":
        return "Draft — human review required. The international shipment appears late under Rule 3.3, but a standard international credit amount is not established by Rule 5.1. Refer for human review (Rule 6.3)."
    manager = " Customer Operations Manager approval is required because the amount exceeds $500 (Rule 5.3)." if amount > 500 else ""
    return f"Draft — human review required. Verified delivery took {days} business days, beyond the {commitment[0]}-business-day {service} commitment (Rule {commitment[1]}; Rule 3.4). Notice was within five business days (Rule 4.1). Proposed maximum standard credit: ${amount:,.2f}, equal to the transportation charge (Rule 5.1).{manager} No credit or customer response may be approved or sent without human review (Section 7)."

def answer(case):
    question = str(case.get("question", ""))[:2000]
    passages = retrieve(question + " " + str(case.get("service", "")))
    required = ["3.4", "4.3", "7", "10"]
    service_rule = {"standard": "3.1", "expedited": "3.2", "international": "3.3"}.get(case.get("service"))
    if service_rule:
        required.append(service_rule)
    if case.get("notice"):
        required.append("4.1")
    if case.get("charge") is not None and case.get("service") in {"standard", "expedited"}:
        required.append("5.1")
    if case.get("requested_refund") is not None:
        required.extend(["5.2", "5.3", "6.1"])
    if case.get("weather"):
        required.extend(["4.2", "5.4"])
    if case.get("wrong_address"):
        required.append("5.5")
    if case.get("legal_or_fraud"):
        required.append("6.2")
    seen = {p["section"] for p in passages}
    for key in required:
        if key not in seen:
            passages.append({"section": key, "text": RULES[key], "score": 0})
            seen.add(key)
    fallback = local_answer(case, passages)
    endpoint = os.getenv("RAKURAKU_LLM_URL", "").strip()
    if not endpoint:
        return {"mode": "retrieval + deterministic policy draft; no LLM connected", "answer": fallback, "passages": passages}
    if any(flag in fallback for flag in ["Evidence incomplete", "Escalate immediately", "Weather exception", "international credit amount"]):
        return {"mode": "retrieval + safety rule gate; local LLM bypassed", "answer": fallback, "passages": passages}
    if urlparse(endpoint).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Only a local LLM endpoint is allowed")
    # Optional OpenAI-compatible local endpoint, for example a locally hosted model.
    payload = json.dumps({"model": os.getenv("RAKURAKU_LLM_MODEL", "local-model"), "messages": [
        {"role": "system", "content": PROMPT},
        {"role": "user", "content": "Fictional case JSON: " + json.dumps(case) + "\nRetrieved passages (only authority): " + json.dumps(passages) + "\nPolicy guardrail result: " + fallback},
    ], "temperature": 0, "max_tokens": 900}).encode()
    req = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as response:
        data = json.load(response)
    draft = data["choices"][0]["message"]["content"]
    if not draft.strip().startswith("Draft — human review required"):
        draft = "Draft — human review required.\n\n" + draft
    if "Rule" not in draft and "Section" not in draft:
        draft = fallback
    return {"mode": "retrieval + local LLM draft", "answer": draft, "guardrail": fallback, "passages": passages}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in {"/", "/index.html"}:
            body = (HERE / "rakuraku_index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/ask":
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size > 20000:
                raise ValueError("Request too large")
            result = answer(json.loads(self.rfile.read(size)))
            body = json.dumps(result).encode()
            status = 200
        except Exception as exc:
            body = json.dumps({"error": str(exc)}).encode()
            status = 400
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

if __name__ == "__main__":
    validate_source()
    print("RakuRaku local demo: http://127.0.0.1:8765", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()

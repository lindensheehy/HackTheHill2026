""""Ask Northwind": an optional assistant that explains the problem, the app and specific cases/alerts.

The engine computes every number; the assistant only reads a compact, numbered evidence pack (E1…, A1…) and
must cite it. It never makes or overrides routing or priority decisions.

- With GEMINI_API_KEY: Gemini (default gemini-3.1-flash-lite, minimal thinking) under a daily call cap.
- Without it (FOSS mode) or over budget: offline keyword retrieval over the same evidence, and a deterministic
  template brief. The UI labels which mode produced the text.
"""

import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import datetime
from functools import lru_cache

from engine import config, cost_model, dashboard, db, usage

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM_PROMPT = """You are "Ask Northwind", the assistant inside a complaint-triage app built for Northwind, a UK
utility (the data is a synthetic hackathon dataset). You help judges, staff and leaders understand the problem,
the evidence and how to use the app.

Rules:
- Use ONLY the numbered evidence items below. Cite them inline like [E3] or [A2]. If the evidence does not
  answer the question, say so briefly and point to the part of the app that would help.
- Tags: OBSERVED = historical data; POLICY = rules we propose or the app applies; ASSUMPTION = scenario inputs;
  SIMULATED = demo data. Keep these distinctions in your wording (e.g. never call a scenario a measured saving).
- Anything causal beyond the evidence is a hypothesis: say "possible" or "worth checking".
- Never make, change or override a routing, ranking or case decision; explain how the app reached it.
- Be concise: at most about 120 words unless asked for more. Plain English, UK spelling, £."""

BRIEF_PROMPT = """Write an investigation brief from the evidence items only. Return JSON exactly like:
{"what_changed": [{"text": "...", "cites": ["A1"]}],
 "possible_explanations": [{"text": "...", "cites": ["A3"]}],
 "check_next": [{"text": "...", "cites": ["A4"]}]}
2-4 bullets per section, each under 30 words, each citing at least one evidence id. Explanations are
hypotheses: start each with "Possibly". Mention if the alert is SIMULATED. No other text."""


# ---- Evidence --------------------------------------------------------------------------------

def _pct(v, d=0):
    return f"{v * 100:.{d}f}%"


@lru_cache(maxsize=1)
def base_evidence():
    """Evidence about the problem and the app. Built once per process from the same aggregates the UI shows."""
    k = dashboard.kpi_header()
    first, tiles = k["first"], {t["key"]: t for t in k["tiles"]}
    t = dashboard.transfer_panel()
    p = t["penalty"]
    spread = t["spread_outside_casetrack"]
    lo = min(s["min"] for s in spread.values())
    hi = max(s["max"] for s in spread.values())
    regs = {r["region"]: r for r in dashboard.regions()["regions"]}
    focus = [regs["Barrowdale"], regs["Dunmoor"]]
    sm = dashboard.smart_meter()
    tp = dashboard.talking_points()
    io = tp["info_only"]
    pilot = tp["ai_pilot"]
    from engine import planner
    pl = planner.defaults()
    per = p["per_avoided"]
    items = [
        ("OBSERVED", f"Two-year decline: SLA breach rate rose from {_pct(first['breach_rate'])} (Oct-24 cohort) to "
                     f"{_pct(tiles['breach_rate']['value'])} ({tiles['breach_rate']['month']} cohort); average days to close went from "
                     f"{first['avg_days_to_close']} to {tiles['avg_days_to_close']['value']}; regulator score from "
                     f"{first['regulator_score']} to {tiles['regulator_score']['value']}. Penalty exposure £2.4M per quarter."),
        ("OBSERVED", f"Transfer penalty (closed complaints): transferred vs not: {p['days']['transferred']:.1f} vs "
                     f"{p['days']['not']:.1f} days, breach {_pct(p['breach']['transferred'])} vs {_pct(p['breach']['not'])}, "
                     f"reopen {_pct(p['reopen']['transferred'])} vs {_pct(p['reopen']['not'])}, cost £121 vs £68. "
                     f"{_pct(p['transfer_share'])} of closed complaints were transferred."),
        ("OBSERVED", f"Transfers depend on where a complaint enters, not what it is: CaseTrack (SYS-04) has no recorded "
                     f"transfers; other entry systems transfer {_pct(lo)}–{_pct(hi)} of complaints across every category, "
                     f"channel, priority and region. Zero recorded transfers does not prove there are no operational handoffs."),
        ("OBSERVED", f"All {t['slowest_1pct']['n']} of the slowest 1% of complaints (over {t['slowest_1pct']['threshold_days']:.0f} days) "
                     f"were transferred. The last 12 months had {t['last_12m']['transfers']:,} transfers."),
        ("POLICY", "The Routing Engine creates every complaint's case in CaseTrack at intake and assigns an owning team by "
                   "category. It shows the likely resolution path, information-only likelihood, and expected days/breach/cost from "
                   "non-transferred vs transferred history. Those are historical expectations, not guarantees. Transfers can't be "
                   "predicted from complaint attributes, so routing is a fixed policy rather than a model."),
        ("POLICY", "Queue ranking is computed from dates as of 2026-09-30 (the stored breach flag says 98% of open cases "
                   "breached, which the dates don't support). Past SLA: score = priority weight (P1 3, P2 2, P3 1) × "
                   "(1 + overdue ÷ SLA days). Not yet past: weight × breach risk × imminence, where breach risk = share of similar cases "
                   "still open at that age that went on to breach. +0.25 if transferred, +0.25 if a live regional alert applies. "
                   "Strict mode sorts by priority, then days overdue."),
        ("OBSERVED", f"Backlog: {pl['backlog']:,} open complaints. Recent inflow about {pl['inflow']:,}/month vs about "
                     f"{pl['closures']:,} closed/month, so the backlog is growing."),
        ("ASSUMPTION", f"The Replay is an assumption-based scenario, not a measured effect of the router. For each transfer "
                       f"assumed avoided it applies the historical difference (£{per['gbp']:.0f}, {per['days']:.1f} days, "
                       f"{per['reopens']:.3f} reopens, {per['breaches']:.3f} breaches). The default is 80% adoption × 60% avoidance "
                       f"(≈ £{t['last_12m']['transfers'] * .48 * per['gbp'] / 1000:.0f}k/year); the upper bound at 100%/100% is "
                       f"£{t['last_12m']['gbp'] / 1000:.0f}k/year."),
        ("POLICY", "Early warning: each region's signals (complaints per category, breach rate, billing exceptions per 1k, "
                   "estimated-read rate) are compared with that region's trailing 6 months (z ≥ 3), with CUSUM for slow "
                   "drift. Alerts on the same signal in 2+ regions are grouped with the systems they share. On real data the "
                   "feed is currently quiet; the 'Inject scenario' button adds a clearly labelled simulated month."),
        ("OBSERVED", "Barrowdale and Dunmoor bill on Aurora Billing (SYS-01, COBOL, two developers left) and MeterHub "
                     f"(SYS-06, estimation unchanged since 2012), with 0% smart meters: estimated reads "
                     f"{_pct(focus[0]['estimated_read_rate'])}/{_pct(focus[1]['estimated_read_rate'])}, billing exceptions "
                     f"{focus[0]['exceptions_per_1k']}/{focus[1]['exceptions_per_1k']} per 1k accounts per month vs ~"
                     f"{sm['exceptions_per_1k']['other']} elsewhere, and {_pct(focus[0]['bill_correction_share'] + focus[1]['bill_correction_share'])} "
                     f"of bill-correction value."),
        ("OBSERVED", f"Smart meters: in the four smart regions, coverage rose from 30% to 81% while estimated reads stayed "
                     f"~{_pct(sm['estimated_read']['other'])} (correlation {sm['penetration_vs_estimated_corr']}). Hypothesis: the benefit "
                     f"arrives by ~30% coverage. 30% in Barrowdale + Dunmoor ≈ {int(sm['accounts_focus'] * .3):,} meters × £148 ≈ "
                     f"£{sm['accounts_focus'] * .3 * 148 / 1e6:.0f}M. Payback depends mostly on the unknown cost of handling a billing exception."),
        ("OBSERVED", f"{_pct(io['share'])} of closed complaints needed information only (~{io['per_year']:,}/year), up to "
                     f"{_pct(max(io['by_category'].values()))} in 'Other'. They reopen no more often "
                     f"({_pct(io['reopen']['info_only'], 1)} vs {_pct(io['reopen']['other'], 1)}). The auto-answer lane (POLICY) "
                     f"answers fresh cases with ≥45% likelihood and a template, then watches for 7 days."),
        ("OBSERVED", f"The 2025 AI chatbot pilot (£640k/year) got worse every month: fully resolved "
                     f"{_pct(pilot[0]['fully_contained_rate'])}→{_pct(pilot[-1]['fully_contained_rate'])}, repeat contact "
                     f"{_pct(pilot[0]['repeat_contact_within_7_days_rate'])}→{_pct(pilot[-1]['repeat_contact_within_7_days_rate'])}; it was paused. "
                     "This app's AI is optional, only explains evidence, and makes no decisions."),
        ("POLICY", "How to use the app: Operations = how bad, where, why (alerts, investigations, system graph); Intake = route "
                   "a new complaint and see its triage card; Replay = assumption-based savings scenario; Triage queue = ranked "
                   "open cases (click one for 'what happened / next / owner / blockers', actions and a customer update), plus the "
                   "auto-answer lane and backlog planner. Keyboard in the queue: / search, j/k move, Enter open, Esc close."),
    ]
    return [{"id": f"E{i + 1}", "kind": k, "text": txt} for i, (k, txt) in enumerate(items)]


def case_evidence(detail):
    c, t, s = detail["case"], detail["triage"], detail.get("summary")
    if c.get("closed"):
        return [{"id": "C1", "kind": "OBSERVED", "text": f"Complaint {c['complaint_id']} is {c['status']}."}]
    items = [
        ("OBSERVED", f"Case {c['complaint_id']}: {s['what_happened']}"),
        ("POLICY", f"Next action: {s['next_action']} Owner: {s['owner']}."),
        ("POLICY", "Blockers: " + " ".join(s["blockers"])),
        ("POLICY", f"Queue rank #{c.get('rank') or '–'}, score {c['queue_score']:.2f}: " + " ".join(c["why"])),
        ("OBSERVED", "Triage reasons: " + " ".join(t["reasons"])),
        ("OBSERVED", f"Legacy vs non-transferred history for this category/priority: {t['expected_days']['legacy']} vs "
                     f"{t['expected_days']['routed']} days, breach {_pct(t['breach_risk']['legacy'])} vs {_pct(t['breach_risk']['routed'])}."),
    ]
    return [{"id": f"C{i + 1}", "kind": k, "text": txt} for i, (k, txt) in enumerate(items)]


def alert_evidence(alert, linked_total=None):
    d = alert["detail"]
    kind = "SIMULATED" if alert["synthetic"] else "OBSERVED"
    fmt = (lambda v: _pct(v, 1)) if alert["signal"].endswith("_rate") else (lambda v: f"{v:,.1f}")
    items = [(kind, f"Alert {alert['alert_id']} ({'simulated demo data' if alert['synthetic'] else 'real data'}), "
                    f"{alert['month']}: {d['summary']}. Method: {d['method']}.")]
    for r in d["per_region"]:
        items.append((kind, f"{r['region']}: {d['label']} = {fmt(r['value'])} vs trailing average {fmt(r['baseline'])} "
                            f"({'CUSUM' if d['method'] == 'cusum' else 'z'} = {r['z']:.1f})."))
    for sn in d["system_notes"]:
        items.append(("OBSERVED", f"Shared system {sn['system']}: {sn['note']}"))
    if linked_total is not None:
        items.append(("OBSERVED", f"{linked_total} open complaints are in the affected regions and related categories "
                                  f"({', '.join(d.get('related_categories') or []) or 'n/a'})."))
    items.append(("POLICY", "Missing evidence: the data has no root-cause field, no destination system for transfers, "
                            "and no system logs, so explanations are hypotheses until checked."))
    return [{"id": f"A{i + 1}", "kind": k, "text": txt} for i, (k, txt) in enumerate(items)]


def _render(items):
    return "\n".join(f"[{i['id']}] ({i['kind']}) {i['text']}" for i in items)


# ---- Gemini ----------------------------------------------------------------------------------

def gemini_enabled():
    return bool(config.GEMINI_API_KEY)


def _post_gemini(body):
    req = urllib.request.Request(
        GEMINI_URL.format(model=config.GEMINI_MODEL), data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": config.GEMINI_API_KEY}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def call_gemini(system, contents, json_mode=False):
    """One generateContent call under the daily cap. Returns text. Raises on budget/HTTP errors."""
    usage.check("gemini", 1)
    gen = {"maxOutputTokens": config.GEMINI_MAX_OUTPUT_TOKENS, "temperature": 0.2,
           "thinkingConfig": {"thinkingLevel": "minimal"}}
    if json_mode:
        gen["responseMimeType"] = "application/json"
    body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents, "generationConfig": gen}
    try:
        data = _post_gemini(body)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")
        if e.code == 400 and "thinking" in detail.lower():
            gen.pop("thinkingConfig")      # model doesn't support thinking control: retry once without it
            data = _post_gemini(body)
        else:
            raise RuntimeError(f"Gemini HTTP {e.code}: {detail[:300]}") from None
    tokens = data.get("usageMetadata", {}).get("totalTokenCount", 0)
    usage.add("gemini", tokens)
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    if not text.strip():
        raise RuntimeError("Gemini returned no text")
    return text


# ---- Chat ------------------------------------------------------------------------------------

_WORD = re.compile(r"[a-z0-9£%]+")
_STOP = set("the a an and or of to in on for is are was were be it this that what why how do does did with by at "
            "from as can i we you our my me about which who when where there their its".split())


def _terms(text):
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 1}


def offline_answer(question, items, focus_ids=()):
    q = _terms(question)
    scored = []
    for it in items:
        overlap = len(q & _terms(it["text"]))
        scored.append((overlap + (2 if it["id"] in focus_ids else 0), it))
    top = [it for score, it in sorted(scored, key=lambda x: -x[0]) if score > 0][:3] or items[:2]
    def clip(t, n=260):
        return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"
    lines = [f"- {clip(it['text'])} [{it['id']}]" for it in top]
    return "The AI assistant is off, so here are the most relevant facts from the app's evidence:\n" + "\n".join(lines)


def ask(question, history=None, case_id=None, alert_id=None, page=None):
    question = (question or "").strip()[:1000]
    if not question:
        raise ValueError("empty question")
    items, focus_ids = list(base_evidence()), []
    if case_id:
        from engine import queue
        detail = queue.case_detail(case_id)
        if detail:
            extra = case_evidence(detail)
            items += extra
            focus_ids += [i["id"] for i in extra]
    if alert_id:
        from jobs.detect_alerts import load_alerts
        a = next((a for a in load_alerts() if a["alert_id"] == alert_id), None)
        if a:
            extra = alert_evidence(a)
            items += extra
            focus_ids += [i["id"] for i in extra]

    mode, note = "offline", None
    if gemini_enabled():
        contents = []
        for turn in (history or [])[-6:]:
            role = "model" if turn.get("role") == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": str(turn.get("text", ""))[:1500]}]})
        where = f"The user is on the '{page}' page." if page else ""
        contents.append({"role": "user", "parts": [{"text": f"{where}\nQuestion: {question}"}]})
        try:
            answer = call_gemini(SYSTEM_PROMPT + "\n\nEvidence:\n" + _render(items), contents)
            mode = "gemini"
        except usage.BudgetExceeded as e:
            answer, note = offline_answer(question, items, focus_ids), str(e)
        except Exception as e:  # network/API problems must never break the app
            answer, note = offline_answer(question, items, focus_ids), f"Gemini unavailable: {e}"
    else:
        answer = offline_answer(question, items, focus_ids)

    ids = {i["id"]: i for i in items}
    cited = [c for c in dict.fromkeys(re.findall(r"\[([ECA]\d+)\]", answer)) if c in ids]
    answer = re.sub(r"\[([ECA]\d+)\]", lambda m: m.group(0) if m.group(1) in ids else "", answer)
    return {"answer": answer.strip(), "mode": mode, "model": config.GEMINI_MODEL if mode == "gemini" else None,
            "note": note, "evidence": [ids[c] for c in cited]}


# ---- Investigation brief ---------------------------------------------------------------------

def template_brief(alert, items):
    d = alert["detail"]
    ids = [i["id"] for i in items]
    region_ids = ids[1:1 + len(d["per_region"])]
    sys_ids = [i["id"] for i in items if i["text"].startswith("Shared system")]
    linked = next((i["id"] for i in items if "open complaints" in i["text"]), ids[0])
    fmt = (lambda v: _pct(v, 1)) if alert["signal"].endswith("_rate") else (
        (lambda v: f"{v:,.0f}") if alert["signal"].startswith("complaints") else (lambda v: f"{v:,.1f}"))
    what = [{"text": f"{d['label']} rose in {r['region']} to {fmt(r['value'])} vs a trailing average of {fmt(r['baseline'])}.", "cites": [rid]}
            for r, rid in zip(d["per_region"], region_ids)]
    expl = [{"text": f"Possibly a fault in {i['text'].split(':')[0].replace('Shared system ', '')}, the system all affected regions share.",
             "cites": [i["id"]]} for i in items if i["id"] in sys_ids]
    expl.append({"text": "Possibly a genuine change in customer demand; the data can't rule it out.", "cites": [ids[-1]]})
    check = [{"text": "Review the linked open complaints in the queue for a common cause.", "cites": [linked]}]
    if sys_ids:
        check.append({"text": "Check the shared systems' batch runs and estimation outputs for this month.", "cites": sys_ids[:2]})
    check.append({"text": "Compare with regions served by other systems for the same month.", "cites": [ids[0]]})
    return {"what_changed": what[:4], "possible_explanations": expl[:4], "check_next": check[:4]}


def _clean_brief(raw, valid):
    out = {}
    for sec in ("what_changed", "possible_explanations", "check_next"):
        bullets = []
        for b in (raw.get(sec) or [])[:4]:
            cites = [c for c in (b.get("cites") or []) if c in valid]
            text = str(b.get("text", "")).strip()[:300]
            if text and cites:           # an uncited claim is dropped, never shown
                bullets.append({"text": text, "cites": cites})
        out[sec] = bullets
    return out


def brief(alert_id, force=False):
    from engine import queue
    from jobs.detect_alerts import load_alerts
    alert = next((a for a in load_alerts() if a["alert_id"] == alert_id), None)
    if alert is None:
        return None
    oc = queue.open_cases(include_auto=True)
    cats = alert["detail"].get("related_categories") or []
    linked = int((oc["region"].isin(alert["regions"]) & oc["category"].isin(cats)).sum())
    items = alert_evidence(alert, linked)
    mode_wanted = "gemini" if gemini_enabled() else "template"
    h = hashlib.sha1((mode_wanted + json.dumps(items, sort_keys=True)).encode()).hexdigest()
    s = db.store()
    if not force:
        rows = s.query("SELECT mode, content, created_ts FROM ai_briefs WHERE alert_id = ? AND evidence_hash = ?", (alert_id, h))
        if rows:
            return {**json.loads(rows[0]["content"]), "mode": rows[0]["mode"], "cached": True,
                    "created": rows[0]["created_ts"], "evidence": items}
    mode, note = "template", None
    content = template_brief(alert, items)
    if mode_wanted == "gemini":
        try:
            text = call_gemini(BRIEF_PROMPT + "\n\nEvidence:\n" + _render(items),
                               [{"role": "user", "parts": [{"text": "Write the brief."}]}], json_mode=True)
            cleaned = _clean_brief(json.loads(text), {i["id"] for i in items})
            if any(cleaned.values()):
                content, mode = cleaned, "gemini"
        except usage.BudgetExceeded as e:
            note = str(e)
        except Exception as e:
            note = f"Gemini unavailable: {e}"
    created = datetime.now().isoformat(timespec="seconds")
    if mode == "gemini":          # templates are free to regenerate; only model output is worth caching
        s.upsert("ai_briefs", ["alert_id", "evidence_hash", "mode", "content", "created_ts"],
                 [(alert_id, h, mode, json.dumps(content), created)], key=["alert_id", "evidence_hash"])
    return {**content, "mode": mode, "cached": False, "created": created, "note": note, "evidence": items,
            "model": config.GEMINI_MODEL if mode == "gemini" else None}


def status():
    return {"gemini": gemini_enabled(), "model": config.GEMINI_MODEL if gemini_enabled() else None,
            "usage": usage.summary()}

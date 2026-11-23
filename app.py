"""Second Look: a discharge safety net for women with possible heart attack symptoms.

Run with:  .venv/bin/streamlit run app.py
"""
import time
from datetime import datetime

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import ecg
from patients import PATIENTS
from rules import (HISTORY_QUESTIONS, NON_CARDIAC_LABELS, SAFETY_NET_MESSAGE, extract_symptoms, second_look,
                   troponin_limit)

st.set_page_config(page_title="Second Look", page_icon="🫀", layout="wide")

LAYOUT = [["I", "AVR", "V1", "V4"], ["II", "AVL", "V2", "V5"], ["III", "AVF", "V3", "V6"]]
DISPLAY = {"AVR": "aVR", "AVL": "aVL", "AVF": "aVF"}
OTHER_LABELS = ["acute coronary syndrome (admit)", "observe and repeat tests"]


def pretty(leads):
    return [DISPLAY.get(l, l) for l in leads]


@st.cache_data
def analyse(record_id, sex, age):
    signals, fs, names = ecg.load(record_id)
    st_dev, _ = ecg.st_deviation(signals, fs, names)
    return signals, fs, names, st_dev, ecg.interpret(st_dev, sex, age)


def ecg_figure(signals, fs, names, flagged):
    fig = make_subplots(rows=3, cols=4, shared_yaxes=True, horizontal_spacing=0.02, vertical_spacing=0.06,
                        subplot_titles=[DISPLAY.get(l, l) for row in LAYOUT for l in row])
    n = int(2.5 * fs)
    t = [i / fs for i in range(n)]
    for r, row in enumerate(LAYOUT, start=1):
        for c, lead in enumerate(row, start=1):
            colour = "#d97706" if lead in flagged else "#1f2937"
            fig.add_trace(go.Scatter(x=t, y=signals[:n, names.index(lead)], line=dict(color=colour, width=1.2),
                                     hoverinfo="skip"), row=r, col=c)
    fig.update_layout(height=420, showlegend=False, margin=dict(l=10, r=10, t=30, b=10),
                      plot_bgcolor="#fff7f7")
    fig.update_xaxes(showticklabels=False, gridcolor="#f5c2c7", dtick=0.2)
    # One shared scale for all leads (as on paper), widened so deep waves are not clipped
    shown = signals[:n]
    lo, hi = min(-1.5, float(shown.min()) - 0.1), max(2.0, float(shown.max()) + 0.1)
    fig.update_yaxes(showticklabels=False, gridcolor="#f5c2c7", dtick=0.5, range=[lo, hi])
    return fig


def log(patient_name, event, kind="action"):
    st.session_state.setdefault("audit", []).append(
        {"time": datetime.now().strftime("%H:%M:%S"), "patient": patient_name, "event": event, "kind": kind})


def safety_net(patient_name):
    st.info(f"📱 **Discharge text sent to {patient_name.split(',')[0]}:**\n\n{SAFETY_NET_MESSAGE}")


def timeline(title, steps, colour):
    st.markdown(f"**{title}**")
    for when, what in steps:
        st.markdown(f"<div style='border-left:4px solid {colour};padding:2px 10px;margin:4px 0'>"
                    f"<b>{when}</b><br>{what}</div>", unsafe_allow_html=True)


def compare_views(p, label, troponin, findings, history, result, headline):
    """Side by side: what the clinician sees on first tests vs what Second Look sees."""
    doc, sl = [], []
    if findings is None:
        doc.append("**ECG:** not done")
        sl.append("**ECG:** not done ❌")
    elif not findings:
        doc.append("**ECG:** no ST elevation ✅")
        sl.append("**ECG:** all 12 leads analysed, no ST elevation. An NSTEMI cannot be ruled out by ECG ⚠️")
    else:
        leads = sorted({l for _, _, ls in findings for l in pretty(ls)})
        doc.append("**ECG:** nothing clearly worrying ✅")
        sl.append(f"**ECG:** subtle ST changes in {', '.join(leads)}, below STEMI thresholds ⚠️")
    if troponin:
        t = troponin[0]
        if t["value"] <= troponin_limit(p["sex"]):
            doc.append(f"**Troponin:** {t['value']} ng/L, below threshold ✅")
        else:
            doc.append(f"**Troponin:** {t['value']} ng/L, above threshold")
        tf = next((f for f in result.findings if "troponin" in f.text.lower()), None)
        if tf is None:
            sl.append(f"**Troponin:** {t['value']} ng/L, valid rule-out ✅")
        elif tf.text.startswith("Only one") and t["hours_from_onset"] < 3:
            sl.append(f"**Troponin:** {t['value']} ng/L is normal, but taken only {t['hours_from_onset']} h "
                      "after symptoms began: too early to rule out ⚠️")
        else:
            sl.append(f"**Troponin:** {tf.text} {'🔴' if tf.level == 'red' else '⚠️'}")
    else:
        doc.append("**Troponin:** not done")
        sl.append("**Troponin:** not done ❌")
    doc.append(f"**Impression:** {label}")
    risks = [f.text.split(":")[0] for f in result.findings
             if any(k in f.text for k in ("pre-eclampsia", "pregnancy", "Pregnant", "menopause", "diabetes", "previous A&E"))]
    sl.append("**History:** " + (" · ".join(risks) + " ⚠️" if risks else
                                  "no record: ask the patient ⚠️" if history is None else "nothing relevant ✅"))
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 👩‍⚕️ What the doctor sees")
        for line in doc:
            st.markdown(line)
        st.markdown("**Verdict: send home** ✅")
    with c2:
        st.markdown("#### 🔍 What Second Look sees")
        for line in sl:
            st.markdown(line)
        st.markdown(f"**Verdict: {headline}**")


def history_from_answers(answers, p):
    """Turn the bedside questions into a history record."""
    history = {
        "pre_eclampsia": answers[0],
        "diabetes": answers[2],
        "previous_visits": [{"months_ago": 2}] if answers[3] else [],
    }
    if answers[1]:
        history["months_since_pregnancy"] = p.get("months_since_pregnancy_if_asked", 6)
    return history


# --- Sidebar ---------------------------------------------------------------
st.sidebar.title("🫀 Second Look")
st.sidebar.caption("A discharge safety net for women with possible heart attack symptoms.")
name = st.sidebar.radio("A&E patient", list(PATIENTS))
page = st.sidebar.radio("View", ["Patient record", "Hospital report"])
if st.sidebar.button("Reset demo"):
    st.session_state.clear()
    st.rerun()
st.sidebar.divider()
st.sidebar.caption("Prototype for the National MedTech Hackathon 2026. Synthetic patients; ECGs are real, "
                   "anonymised recordings from PTB-XL (PhysioNet, CC BY 4.0). Not for clinical use.")

p = PATIENTS[name]
state = st.session_state.setdefault(name, {
    "history": p["history"], "ecg": p["ecg"], "troponin": list(p["troponin"]),
    "orders_used": 0, "stage": "assess", "logged": False,
})

# --- Hospital report -------------------------------------------------------
if page == "Hospital report":
    st.title("Hospital report")
    st.caption("This session's Second Look decisions. In a real deployment this shows how often women "
               "were nearly discharged before the work-up was complete.")
    audit = st.session_state.get("audit", [])
    m1, m2, m3 = st.columns(3)
    m1.metric("Discharges checked", sum(e["kind"] == "attempt" for e in audit))
    m2.metric("Second Look fired", sum(e["kind"] == "fired" for e in audit))
    m3.metric("Stayed silent", sum(e["kind"] == "silent" for e in audit))
    st.markdown("##### Session log")
    if audit:
        st.dataframe([{k: v for k, v in e.items() if k != "kind"} for e in audit], width="stretch", hide_index=True)
    else:
        st.info("No discharge attempts yet. Open a patient and press Discharge.")
    st.stop()

# --- Patient record --------------------------------------------------------
st.title(f"{name}  ·  {'Female' if p['sex'] == 'F' else 'Male'}")
st.write(p["story"])

left, right = st.columns([1, 1])
with left:
    st.subheader("Triage")
    note = st.text_area("Triage note (free text)", p["triage_note"], key=f"{name}-note", height=80)
    symptoms = extract_symptoms(note)
    st.write("**Heart-type symptoms recognised:** " + (", ".join(symptoms) if symptoms else "none"))
    st.subheader("Troponin (hs-cTn)")
    if state["troponin"]:
        st.table([{"Hours after onset": t["hours_from_onset"], "Result (ng/L)": t["value"]} for t in state["troponin"]])
    else:
        st.warning("No troponin taken.")
with right:
    st.subheader("History")
    hist = state["history"]
    if hist is None:
        st.warning("No record available for this patient.")
    else:
        items = [k.replace("_", " ") for k, v in hist.items() if v and k not in ("previous_visits", "months_since_pregnancy")]
        if hist.get("months_since_pregnancy") is not None:
            items.insert(0, f"gave birth {hist['months_since_pregnancy']} months ago")
        st.write(", ".join(items) if items else "Nothing relevant recorded.")
        st.write(f"Previous similar A&E visits: {len(hist.get('previous_visits', []))}")

st.subheader("12-lead ECG")
if state["ecg"] is None:
    findings = None
    st.warning("No ECG recorded for this visit.")
else:
    signals, fs, names, st_dev, findings = analyse(state["ecg"], p["sex"], p["age"])
    flagged = {lead for _, _, leads in findings for lead in leads}
    st.caption(p["ecg_note"] + ". Leads flagged by Second Look are drawn in amber.")
    st.plotly_chart(ecg_figure(signals, fs, names, flagged), width="stretch")
    with st.expander("ST measurements (mV, approximate)"):
        st.table({DISPLAY.get(k, k): [round(v, 3)] for k, v in st_dev.items()})

# --- Discharge -------------------------------------------------------------
st.divider()
st.subheader("Discharge")
labels = sorted(NON_CARDIAC_LABELS) + OTHER_LABELS
label = st.selectbox("Discharge diagnosis", labels, index=labels.index(p["default_label"]))

if st.button("Discharge patient", type="primary"):
    state["stage"] = "checked"
    state["logged"] = False
    log(name, f"Discharge attempted: {label}", "attempt")

if state["stage"] != "checked":
    st.stop()

patient_now = dict(p, history=state["history"], symptoms=symptoms, troponin=state["troponin"])
result = second_look(patient_now, label, findings, pretty)

if not result.triggered or result.level == "clear":
    st.success("Discharged. Second Look found no gaps in the work-up.")
    if not state["logged"]:
        log(name, "Second Look silent: discharged", "silent")
        state["logged"] = True
    if symptoms:
        safety_net(name)
    st.stop()

if not state["logged"]:
    log(name, f"Second Look fired ({len(result.findings)} findings)", "fired")
    state["logged"] = True

box = st.error if result.level == "red" else st.warning
if any(f.text.startswith("Troponin rising") for f in result.findings):
    headline = "Heart attack (NSTEMI) likely: do not discharge."
elif result.level == "red":
    headline = "A heart attack has not been ruled out: urgent senior review."
else:
    headline = "A heart attack (NSTEMI) has not been ruled out."
box(f"**⚠️ Second Look: before you discharge {name.split(',')[0]}**\n\n{headline}")
first_tests = [t for t in state["troponin"][:1]]
compare_views(p, label, first_tests if not any(f.text.startswith("Troponin rising") for f in result.findings)
              else state["troponin"], findings, state["history"], result, headline)
with st.expander("Details and guideline evidence", expanded=True):
    for f in result.findings:
        st.markdown(f"{'🔴' if f.level == 'red' else '🟠'} {f.text}"
                    + (f"  \n**Next step:** {f.action}" if f.action else ""))
        if f.ref:
            st.caption(f"📖 {f.ref}")

if p.get("timeline_without"):
    with st.expander(f"Why it matters: {name.split(',')[0]}'s two possible nights"):
        t1, t2 = st.columns(2)
        with t1:
            timeline("Without Second Look", p["timeline_without"], "#dc2626")
        with t2:
            timeline("With Second Look", p["timeline_with"], "#16a34a")

if result.questions:
    st.write("**No history available. Ask the patient:**")
    answers = [st.checkbox(q, key=f"{name}-q{i}") for i, q in enumerate(HISTORY_QUESTIONS)]
    if st.button("Update record"):
        state["history"] = history_from_answers(answers, p)
        log(name, "History taken at bedside")
        st.rerun()

orders = p.get("troponin_orders", [])
can_order_trop = state["orders_used"] < len(orders)
a, b, c, d = st.columns(4)
if state["ecg"] is None and p.get("ecg_if_done") and a.button("Do ECG now"):
    state["ecg"] = p["ecg_if_done"]
    log(name, "ECG done")
    st.rerun()
trop_label = "Order repeat troponin" if state["troponin"] else "Order troponin"
if b.button(trop_label, disabled=not can_order_trop):
    test = orders[state["orders_used"]]
    if state["troponin"]:
        with st.spinner("⏱ Repeat troponin: 3 hours later…"):
            time.sleep(1.5)
    state["troponin"].append(test)
    state["orders_used"] += 1
    log(name, f"{trop_label}: {test['value']} ng/L")
    st.rerun()
if c.button("Request senior review"):
    log(name, "Senior review requested")
    st.info("Senior review requested. Patient stays in A&E.")
with d:
    reason = st.selectbox("Discharge anyway: reason", ["—", "Senior reviewed and agreed",
                          "Patient declined further tests", "Clear alternative diagnosis"])
    if reason != "—" and st.button("Confirm discharge"):
        log(name, f"Discharged despite Second Look: {reason}")
        st.success("Discharged. Reason recorded.")
        safety_net(name)


"""Export everything the website needs to docs/data/data.json.

Python stays the source of truth: the ECG signal processing runs here, and the
rules' thresholds, phrases and references are copied from rules.py so the
browser engine (docs/engine.js) uses exactly the same values.

Run from the repo root after changing rules.py, ecg.py, patients.py or data/:
    .venv/bin/python scripts/export_web.py
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ecg  # noqa: E402
import rules  # noqa: E402
from patients import PATIENTS  # noqa: E402

OUT = ROOT / "docs" / "data" / "data.json"
DISPLAY_FS = 250  # Hz; plenty for drawing, halves the file size
SEGMENT_S = 2.5
# Standard 12-lead print layout: each column shows the next 2.5 s
COLUMNS = [["I", "II", "III"], ["AVR", "AVL", "AVF"], ["V1", "V2", "V3"], ["V4", "V5", "V6"]]
OTHER_LABELS = ["acute coronary syndrome (admit)", "observe and repeat tests"]

# PTB-XL metadata for the bundled records (from ptbxl_database.csv)
RECORD_INFO = {
    "00007_hr": {"ptbxl_id": 7, "sex": "M", "age": 54, "label": "Normal ECG"},
    "00033_hr": {"ptbxl_id": 33, "sex": "F", "age": 49, "label": "Normal ECG"},
    "00044_hr": {"ptbxl_id": 44, "sex": "F", "age": 45, "label": "Normal ECG"},
    "00081_hr": {"ptbxl_id": 81, "sex": "F", "age": 46, "label": "Normal ECG"},
    "00514_hr": {"ptbxl_id": 514, "sex": "F", "age": 61, "label": "Acute inferolateral MI"},
    "03956_hr": {"ptbxl_id": 3956, "sex": "F", "age": 61, "label": "Acute inferior MI"},
    "05329_hr": {"ptbxl_id": 5329, "sex": "F", "age": 57, "label": "Acute anteroseptal MI (with LVH)"},
}


def export_record(record_id):
    signals, fs, names = ecg.load(record_id)
    st_dev, peaks = ecg.st_deviation(signals, fs, names)
    filtered = ecg._filter(signals, fs)
    step = int(fs // DISPLAY_FS)
    seg = int(SEGMENT_S * fs)

    def microvolts(x):
        return [int(round(v * 1000)) for v in x[::step]]

    leads = {}
    for col, group in enumerate(COLUMNS):
        start = col * seg
        for name in group:
            leads[name] = {"start_s": col * SEGMENT_S,
                           "uv": microvolts(filtered[start:start + seg, names.index(name)])}
    rhythm = microvolts(filtered[:4 * seg, names.index("II")])
    shown = np.concatenate([np.array(v["uv"]) for v in leads.values()] + [np.array(rhythm)]) / 1000
    return {
        **RECORD_INFO[record_id],
        "fs": DISPLAY_FS,
        "leads": leads,
        "rhythm_ii": rhythm,
        "r_peaks_s": [round(p / fs, 4) for p in peaks],
        "st_mv": st_dev,
        "range_mv": [float(np.floor(min(shown.min(), -1.0) * 2) / 2), float(np.ceil(max(shown.max(), 1.5) * 2) / 2)],
    }


def rules_config():
    return {
        "symptom_phrases": rules.SYMPTOM_PHRASES,
        "cardiac_symptoms": sorted(rules.CARDIAC_SYMPTOMS),
        "non_cardiac_labels": sorted(rules.NON_CARDIAC_LABELS),
        "other_labels": OTHER_LABELS,
        "very_low_troponin": rules.VERY_LOW_TROPONIN,
        "min_hours_for_single_test": rules.MIN_HOURS_FOR_SINGLE_TEST,
        "rising_delta": rules.RISING_DELTA,
        "troponin_url": rules.TROPONIN_URL,
        "repeat_window_months": rules.REPEAT_WINDOW_MONTHS,
        "negations": rules.NEGATIONS,
        "women_risk_factors": list(rules.WOMEN_RISK_FACTORS.items()),
        "general_risk_factors": list(rules.GENERAL_RISK_FACTORS.items()),
        "refs": rules.REFS,
        "safety_net_message": rules.SAFETY_NET_MESSAGE,
        "history_questions": rules.HISTORY_QUESTIONS,
        "ecg": {
            "groups": ecg.GROUPS,
            "subtle_mv": ecg.SUBTLE_MV,
            "subtle_v1_v3_margin": ecg.SUBTLE_V1_V3_MARGIN,
            "depression_mv": ecg.DEPRESSION_MV,
            "st_offset_s": 0.10,
            "baseline_offset_s": -0.08,
        },
    }


def build():
    return {
        "rules": rules_config(),
        "patients": PATIENTS,
        "records": {rid: export_record(rid) for rid in RECORD_INFO},
    }


# --- Parity cases: the browser engine must give the same answers as Python ---

def pretty(leads):
    return [{"AVR": "aVR", "AVL": "aVL", "AVF": "aVF"}.get(l, l) for l in leads]


def result_dict(r):
    return {"triggered": r.triggered, "level": r.level, "questions": r.questions,
            "findings": [[f.level, f.text, f.action, f.ref] for f in r.findings]}


NOTES = [p["triage_note"] for p in PATIENTS.values()] + [
    "No chest pain, came in for a sick note", "Denies breathlessness. Feels sick.", "sobbing after an argument",
    "SOB on stairs", "Chest pain but no nausea", "No energy for a week", "jawline rash, no jaw pain",
    "Tight chest radiating to left arm, clammy and dizzy", "nil palpitations; heart racing earlier",
    "Weakness and vomiting since lunch", "not tired, just weak", "Pain between shoulder blades: no sweating",
    "", "heartburn after curry", "Pressure in chest without sweating but very lightheaded",
]


def build_parity_cases():
    cases = {"symptoms": [], "interpret": [], "second_look": []}
    for note in NOTES:
        cases["symptoms"].append({"note": note, "expected": rules.extract_symptoms(note)})
    st_by_record = {}
    for rid in RECORD_INFO:
        signals, fs, names = ecg.load(rid)
        st_by_record[rid], _ = ecg.st_deviation(signals, fs, names)
        for sex in ("F", "M"):
            for age in (35, 50):
                cases["interpret"].append({"record": rid, "sex": sex, "age": age,
                                           "expected": [list(f) for f in ecg.interpret(st_by_record[rid], sex, age)]})
    histories = ["orig", None, {"pre_eclampsia": True, "diabetes": True, "previous_visits": []},
                 {"months_since_pregnancy": 4, "previous_visits": [{"months_ago": 2}]},
                 {"early_menopause": True, "gestational_diabetes": True, "previous_visits": [{"months_ago": 8}]}]
    for name, p in PATIENTS.items():
        troponins = [p["troponin"], p["troponin"] + p.get("troponin_orders", []), [],
                     [{"hours_from_onset": 4, "value": 25}], [{"hours_from_onset": 4, "value": 4}],
                     [{"hours_from_onset": 1, "value": 3}], [{"hours_from_onset": 2, "value": 40},
                                                              {"hours_from_onset": 5, "value": 38}]]
        for label in (p["default_label"], "acute coronary syndrome (admit)"):
            for trop in troponins:
                for hist in histories:
                    for rid in [None] + list(RECORD_INFO):
                        history = p["history"] if hist == "orig" else hist
                        symptoms = rules.extract_symptoms(p["triage_note"])
                        patient = dict(p, history=history, troponin=trop, symptoms=symptoms)
                        findings = None if rid is None else ecg.interpret(st_by_record[rid], p["sex"], p["age"])
                        r = rules.second_look(patient, label, findings, pretty)
                        cases["second_look"].append({
                            "patient": name, "label": label, "troponin": trop, "history": history,
                            "symptoms": symptoms, "record": rid, "expected": result_dict(r)})
    return cases


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), separators=(",", ":"), ensure_ascii=False))
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB)")

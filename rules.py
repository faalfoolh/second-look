"""Second Look rules engine.

Runs when a clinician tries to discharge a patient with a non-cardiac label.
Returns the checks that are outstanding, or an empty list when the work-up is
complete. Missing information is never treated as safe: it becomes a question.

Clinical thresholds below are placeholders. They must be checked against local
assays and guidelines by clinicians before any real use.
"""
import re
from dataclasses import dataclass, field

# --- Clinical content: all thresholds and wording live here ---------------

# Free-text triage: phrases a nurse might type, mapped to a standard symptom
SYMPTOM_PHRASES = {
    "chest pain": ["chest pain", "chest ache", "pain in chest", "chest discomfort", "burning chest"],
    "chest tightness": ["chest tight", "tight chest", "pressure in chest", "heavy chest", "chest pressure"],
    "jaw pain": ["jaw"],
    "arm pain": ["arm pain", "arm ache", "pain down arm", "left arm", "arms ache", "arm heavy"],
    "back pain": ["back pain", "back ache", "backache", "back tight", "between shoulder blades", "upper back"],
    "neck pain": ["neck pain", "neck ache", "throat tight"],
    "nausea": ["nausea", "nauseous", "feel sick", "feels sick", "feeling sick", "being sick", "vomit"],
    "breathlessness": ["breathless", "short of breath", "sob", "can't catch breath", "cant catch breath", "breathing difficult"],
    "sweating": ["sweat", "clammy"],
    "unusual fatigue": ["tired", "exhausted", "fatigue", "no energy", "weak", "weakness"],
    "epigastric pain": ["epigastric", "indigestion", "heartburn", "upper stomach", "burning"],
    "palpitations": ["palpitation", "racing heart", "heart racing", "fluttering"],
    "dizziness": ["dizzy", "lightheaded", "light-headed", "faint"],
}

CARDIAC_SYMPTOMS = {
    "chest pain", "chest tightness", "jaw pain", "arm pain", "back pain",
    "neck pain", "nausea", "breathlessness", "sweating", "unusual fatigue",
    "epigastric pain", "palpitations", "dizziness",
}

NON_CARDIAC_LABELS = {
    "anxiety / panic attack", "gastro-oesophageal reflux", "musculoskeletal chest pain",
    "chest wall pain", "viral illness", "indigestion", "stress", "dental pain",
}

# Single-test rule-out (ESC 0h pathway style): a very low first hs-troponin
# taken at least 3 h after symptom onset can rule out MI without a repeat.
VERY_LOW_TROPONIN = 5  # ng/L, assay-specific placeholder
MIN_HOURS_FOR_SINGLE_TEST = 3
RISING_DELTA = 3  # ng/L between first and latest test, placeholder
# Sex-specific 99th percentile upper reference limits (Abbott Architect hs-cTnI
# values, used as placeholders; every assay has its own)
TROPONIN_URL = {"F": 16, "M": 34}
REPEAT_WINDOW_MONTHS = 6

# Words that cancel a symptom when they come before it in the same clause
NEGATIONS = r"\b(no|not|denies|denied|without|nil)\b"

WOMEN_RISK_FACTORS = {
    "pre_eclampsia": "History of pre-eclampsia: a recognised heart risk factor in women.",
    "gestational_hypertension": "Hypertension in pregnancy: a recognised heart risk factor in women.",
    "gestational_diabetes": "Gestational diabetes: raises later cardiovascular risk.",
    "early_menopause": "Menopause before 45: raises cardiovascular risk.",
}
GENERAL_RISK_FACTORS = {
    "diabetes": "Diabetes: heart attacks may present without typical chest pain.",
}
# Evidence shown beside each warning
REFS = {
    "troponin": "ESC 2023 ACS guidelines: hs-troponin 0h/1h or 0h/2h algorithm; single-test rule-out only if very low and chest pain began >3 h earlier",
    "troponin_sex": "High-STEACS (Shah et al., BMJ 2015): a female-specific hs-troponin threshold identified twice as many women with myocardial infarction",
    "ecg": "Fourth Universal Definition of MI (2018): ST elevation thresholds, women ≥1.5 mm in V2–V3",
    "no_ecg": "NICE CG95: anyone with suspected acute coronary syndrome should have a 12-lead ECG as soon as possible",
    "ecg_subtle": "Women's ST elevation is often smaller (VIRGO study, JAHA 2018); STEMI criteria miss many occlusions in both sexes",
    "pregnancy_risk": "ESC 2024 hypertension guidelines: pregnancy complications are sex-specific cardiovascular risk modifiers",
    "scad": "ESC position paper on SCAD (2018): SCAD causes many heart attacks in young women and around pregnancy",
    "menopause": "ESC 2021 prevention guidelines: premature menopause raises cardiovascular risk",
    "diabetes": "ESC 2023 ACS guidelines: patients with diabetes often present without typical chest pain",
    "repeat": "Repeat attendance with unexplained symptoms is a recognised red flag for missed diagnosis",
}

SAFETY_NET_MESSAGE = (
    "You have been seen in A&E today. Please call 999 straight away if you get pain or pressure in your "
    "chest, jaw, neck, arm or back, breathlessness, sweating, or nausea that does not go away. "
    "In women these can be signs of a heart attack even without severe chest pain. "
    "If you are worried, do not wait: it is always right to come back."
)

HISTORY_QUESTIONS = [
    "Ever had pre-eclampsia or high blood pressure in pregnancy?",
    "Pregnant now, or given birth in the last 12 months?",
    "Diabetes?",
    "Been to A&E with similar symptoms before?",
]

# ---------------------------------------------------------------------------


@dataclass
class Finding:
    level: str  # "red" or "amber"
    text: str
    action: str = ""
    ref: str = ""


@dataclass
class Result:
    triggered: bool
    findings: list = field(default_factory=list)
    questions: list = field(default_factory=list)

    @property
    def level(self):
        if any(f.level == "red" for f in self.findings):
            return "red"
        return "amber" if self.findings or self.questions else "clear"


def _phrase_pattern(phrase):
    # Short phrases ("sob", "jaw", "weak") must be whole words so "sobbing" or
    # "jawline" do not count; longer ones may be word stems ("sweat" -> "sweating").
    tail = r"\b" if len(phrase) <= 4 else ""
    return re.compile(r"\b" + re.escape(phrase) + tail)


def _negated(clause, start):
    return re.search(NEGATIONS, clause[:start]) is not None


def extract_symptoms(note):
    """Map a free-text triage note to standard symptoms, skipping negated ones
    ("no chest pain", "denies breathlessness")."""
    found = set()
    for clause in re.split(r"[.,;:\n]|\bbut\b", note.lower()):
        for sym, phrases in SYMPTOM_PHRASES.items():
            for ph in phrases:
                m = _phrase_pattern(ph).search(clause)
                if m and (ph.startswith("no ") or not _negated(clause, m.start())):
                    found.add(sym)
                    break
    return sorted(found)


def has_cardiac_symptoms(patient):
    return bool(CARDIAC_SYMPTOMS & set(patient["symptoms"]))


def troponin_limit(sex):
    return TROPONIN_URL.get(sex, min(TROPONIN_URL.values()))


def check_troponin(patient):
    tests = patient["troponin"]
    if not tests:
        return Finding("red", "No troponin taken.", "Order troponin", REFS["troponin"])
    url = troponin_limit(patient["sex"])
    first, last = tests[0]["value"], tests[-1]["value"]
    if len(tests) > 1 and last - first >= RISING_DELTA:
        return Finding("red", f"Troponin rising: {first} → {last} ng/L.", "Refer to cardiology", REFS["troponin"])
    high = [t["value"] for t in tests if t["value"] > url]
    if high:
        who = "women" if patient["sex"] == "F" else "men"
        return Finding("red", f"Troponin {max(high)} ng/L is above the upper limit for {who} ({url} ng/L).",
                       "Refer to cardiology", REFS["troponin_sex"])
    if len(tests) == 1:
        t = tests[0]
        if t["value"] < VERY_LOW_TROPONIN and t["hours_from_onset"] >= MIN_HOURS_FOR_SINGLE_TEST:
            return None  # valid single-test rule-out
        if t["hours_from_onset"] < MIN_HOURS_FOR_SINGLE_TEST:
            why = (f"Normal result, but taken only {t['hours_from_onset']} h after symptoms began: "
                   "too early to rule out a heart attack. Troponin can take hours to rise.")
        else:
            why = "Not low enough to rule out a heart attack on a single test."
        return Finding(
            "amber",
            f"Only one troponin ({t['value']} ng/L, {t['hours_from_onset']} h after onset). {why}",
            "Order repeat troponin",
            REFS["troponin"],
        )
    return None


def check_ecg(ecg_findings, lead_list):
    if ecg_findings is None:
        return [Finding("red", "No ECG recorded.", "Do a 12-lead ECG now", REFS["no_ecg"])]
    out = []
    for kind, group, leads in ecg_findings:
        leads_txt = ", ".join(lead_list(leads))
        if kind == "stemi":
            out.append(Finding("red", f"ECG meets STEMI criteria in {group} leads ({leads_txt}).", "Activate cath lab pathway", REFS["ecg"]))
        elif kind == "subtle":
            out.append(Finding("amber", f"Subtle ST elevation in {group} leads ({leads_txt}), below STEMI thresholds.", "Senior ECG review", REFS["ecg_subtle"]))
        elif kind == "depression":
            out.append(Finding("amber", f"ST depression in {group} leads ({leads_txt}).", "Senior ECG review", REFS["ecg"]))
    return out


def check_history(patient):
    history = patient.get("history")
    if history is None:
        return [], HISTORY_QUESTIONS
    out = []
    if patient["sex"] == "F":
        if history.get("months_since_pregnancy") is not None and history["months_since_pregnancy"] <= 12:
            out.append(Finding(
                "red",
                f"Pregnant or gave birth {history['months_since_pregnancy']} months ago: consider SCAD "
                "(spontaneous coronary artery dissection) even with normal tests.",
                "Senior review",
                REFS["scad"],
            ))
        for key, text in WOMEN_RISK_FACTORS.items():
            if history.get(key):
                ref = REFS["menopause"] if key == "early_menopause" else REFS["pregnancy_risk"]
                out.append(Finding("amber", text, ref=ref))
    for key, text in GENERAL_RISK_FACTORS.items():
        if history.get(key):
            out.append(Finding("amber", text, ref=REFS["diabetes"]))
    visits = [v for v in history.get("previous_visits", []) if v["months_ago"] <= REPEAT_WINDOW_MONTHS]
    if visits:
        out.append(Finding("amber", f"{len(visits)} previous A&E visit(s) with similar symptoms in the last {REPEAT_WINDOW_MONTHS} months.", ref=REFS["repeat"]))
    return out, []


def second_look(patient, discharge_label, ecg_findings, lead_list=lambda l: l):
    """Main entry point: run at the moment of discharge."""
    if discharge_label not in NON_CARDIAC_LABELS or not has_cardiac_symptoms(patient):
        return Result(triggered=False)

    findings = []
    trop = check_troponin(patient)
    if trop:
        findings.append(trop)
    findings += check_ecg(ecg_findings, lead_list)
    history_findings, questions = check_history(patient)

    # Risk factors only matter when something in the work-up is also outstanding;
    # a complete, normal work-up stays silent.
    workup_gap = bool(findings) or bool(questions)
    if workup_gap:
        findings += history_findings
    else:
        findings += [f for f in history_findings if f.level == "red"]

    return Result(triggered=True, findings=findings, questions=questions)

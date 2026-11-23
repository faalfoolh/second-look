import pytest

import ecg
from patients import PATIENTS
from rules import extract_symptoms, second_look


@pytest.mark.parametrize("note, expected", [
    ("Chest pain and short of breath", ["breathlessness", "chest pain"]),
    ("No chest pain, came in for a sick note", []),
    ("Denies breathlessness. Feels sick.", ["nausea"]),
    ("sobbing after an argument", []),
    ("SOB on stairs", ["breathlessness"]),
    ("Chest pain but no nausea", ["chest pain"]),
    ("No energy for a week", ["unusual fatigue"]),
    ("Ache between shoulder blades, sweating", ["back pain", "sweating"]),
])
def test_extract_symptoms(note, expected):
    assert extract_symptoms(note) == expected


def run(name, **overrides):
    p = dict(PATIENTS[name], **overrides)
    p["symptoms"] = extract_symptoms(p["triage_note"])
    findings = None
    if p["ecg"]:
        signals, fs, names = ecg.load(p["ecg"])
        st_dev, _ = ecg.st_deviation(signals, fs, names)
        findings = ecg.interpret(st_dev, p["sex"], p["age"])
    return second_look(p, p["default_label"], findings)


def texts(result):
    return " | ".join(f.text for f in result.findings)


def test_sarah_early_troponin_fires_amber():
    r = run("Sarah, 44")
    assert r.level == "amber"
    assert "too early" in texts(r)
    assert "pre-eclampsia" in texts(r)


def test_sarah_repeat_troponin_rising_is_red():
    r = run("Sarah, 44", troponin=PATIENTS["Sarah, 44"]["troponin"] + PATIENTS["Sarah, 44"]["troponin_orders"])
    assert r.level == "red"
    assert "Troponin rising: 6 → 41" in texts(r)


def test_fully_worked_up_patients_stay_silent():
    for name in ("Emma, 52", "James, 48"):
        assert run(name).level == "clear", name


def test_no_history_becomes_questions():
    r = run("Aisha, 38")
    assert r.questions and r.level == "amber"


def test_linda_missing_ecg_is_red():
    r = run("Linda, 61")
    assert r.level == "red"
    assert "No ECG recorded" in texts(r)


def test_linda_ecg_shows_subtle_inferior_changes():
    r = run("Linda, 61", ecg=PATIENTS["Linda, 61"]["ecg_if_done"])
    assert "Subtle ST elevation in inferior leads" in texts(r)
    assert "ST depression in lateral leads" in texts(r)
    assert "STEMI criteria" not in texts(r)


def test_single_high_troponin_uses_female_limit():
    base = dict(PATIENTS["Emma, 52"], symptoms=["chest pain"])
    woman = second_look(dict(base, troponin=[{"hours_from_onset": 4, "value": 25}]), base["default_label"], [])
    man = second_look(dict(base, sex="M", troponin=[{"hours_from_onset": 4, "value": 25}]), base["default_label"], [])
    assert woman.level == "red" and "upper limit for women (16 ng/L)" in texts(woman)
    assert "upper limit" not in texts(man)


def test_cardiac_label_or_no_symptoms_does_not_trigger():
    p = dict(PATIENTS["Sarah, 44"], symptoms=["chest pain"])
    assert not second_look(p, "acute coronary syndrome (admit)", []).triggered
    assert not second_look(dict(p, symptoms=[]), p["default_label"], []).triggered

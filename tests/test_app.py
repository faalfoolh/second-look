"""Click through every patient in the running app and check nothing errors."""
from streamlit.testing.v1 import AppTest

from patients import PATIENTS


def fresh():
    at = AppTest.from_file("../app.py", default_timeout=60)
    at.run()
    return at


def button(at, label):
    return next(b for b in at.button if b.label == label)


def test_every_patient_discharges_without_error():
    for name in PATIENTS:
        at = fresh()
        at.sidebar.radio[0].set_value(name).run()
        button(at, "Discharge patient").click().run()
        assert not at.exception, name


def test_linda_do_ecg_reveals_subtle_changes():
    at = fresh()
    at.sidebar.radio[0].set_value("Linda, 61").run()
    button(at, "Discharge patient").click().run()
    assert any("No ECG recorded" in m.value for m in at.markdown)
    button(at, "Do ECG now").click().run()
    assert not at.exception
    assert any("Subtle ST elevation in inferior leads" in m.value for m in at.markdown)


def test_hospital_report_counts_attempts():
    at = fresh()
    button(at, "Discharge patient").click().run()
    at.sidebar.radio[1].set_value("Hospital report").run()
    assert not at.exception
    assert at.metric[0].value == "1"

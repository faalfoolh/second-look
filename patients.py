"""Synthetic demo patients. ECGs are real, anonymised PTB-XL recordings
(PhysioNet, CC BY 4.0) attached for illustration; the stories are invented.

Fields ending in _if_done / _orders / _if_asked hold what the demo reveals
when the clinician orders a test or asks a question.
"""

PATIENTS = {
    "Sarah, 44": {
        "sex": "F", "age": 44,
        "story": "Came to A&E with fatigue, breathlessness and chest pain. ECG and troponin done straight away: "
                 "On admission her ECG shows no ST elevation and her troponin is below the threshold. "
                 "She is anxious and breathing fast, so a panic attack seems likely.",
        "triage_note": "Chest pain, breathless, exhausted for 2 days. Very anxious, breathing fast.",
        "ecg": "00081_hr", "ecg_note": "PTB-XL record 81 (woman, 46). No ST elevation",
        "troponin": [{"hours_from_onset": 1.5, "value": 6}],
        "troponin_orders": [{"hours_from_onset": 4.5, "value": 41}],
        "history": {"pre_eclampsia": True, "previous_visits": [{"months_ago": 3}]},
        "default_label": "anxiety / panic attack",
        "timeline_without": [
            ("21:00", "No ST elevation on ECG; troponin below threshold; symptoms fit a panic attack"),
            ("21:40", "Sent home with 'anxiety / panic attack'"),
            ("Day 2", "Pain and breathlessness return; she waits, told it was anxiety"),
            ("Day 3", "Collapses at home; 999; heart attack with permanent heart muscle damage"),
        ],
        "timeline_with": [
            ("21:40", "Discharge pressed; Second Look: troponin too early to rule out, pre-eclampsia, repeat visit"),
            ("21:41", "Repeat troponin ordered; she stays in A&E"),
            ("00:40", "Troponin rising 6 → 41 ng/L: heart attack (NSTEMI)"),
            ("Same night", "Cardiology review and treatment, about 2 days earlier"),
        ],
    },
    "Emma, 52": {
        "sex": "F", "age": 52,
        "story": "Burning chest discomfort after a large meal. Fully worked up.",
        "triage_note": "Burning chest discomfort and heartburn after a large meal.",
        "ecg": "00033_hr", "ecg_note": "PTB-XL record 33 (woman, 49, normal ECG)",
        "troponin": [{"hours_from_onset": 3, "value": 3}, {"hours_from_onset": 6, "value": 3}],
        "history": {"previous_visits": []},
        "default_label": "gastro-oesophageal reflux",
    },
    "Aisha, 38": {
        "sex": "F", "age": 38,
        "story": "Breathless and nauseous. Visiting from another city: no record available.",
        "triage_note": "Short of breath on stairs, nauseous, exhausted for 2 days. Visiting family.",
        "ecg": "00044_hr", "ecg_note": "PTB-XL record 44 (woman, 45, normal ECG)",
        "troponin": [{"hours_from_onset": 1.5, "value": 6}],
        "troponin_orders": [{"hours_from_onset": 4.5, "value": 6}],
        "history": None,
        "months_since_pregnancy_if_asked": 4,
        "default_label": "anxiety / panic attack",
    },
    "Linda, 61": {
        "sex": "F", "age": 61,
        "story": "Upper stomach discomfort, nausea and an ache between her shoulder blades since this afternoon. "
                 "Triage was busy and no ECG was done. One troponin was taken an hour after the pain began.",
        "triage_note": "Burning upper stomach pain, feels sick, ache between shoulder blades. No chest pain.",
        "ecg": None, "ecg_if_done": "03956_hr",
        "ecg_note": "PTB-XL record 3956 (woman, 61, acute inferior myocardial infarction)",
        "troponin": [{"hours_from_onset": 1, "value": 9}],
        "troponin_orders": [{"hours_from_onset": 4, "value": 34}],
        "history": {"diabetes": True, "previous_visits": []},
        "default_label": "indigestion",
    },
    "James, 48": {
        "sex": "M", "age": 48,
        "story": "Sharp left chest pain after lifting at the gym. Fully worked up.",
        "triage_note": "Sharp left-sided chest pain after lifting weights at the gym, worse on movement.",
        "ecg": "00007_hr", "ecg_note": "PTB-XL record 7 (man, 54, normal ECG)",
        "troponin": [{"hours_from_onset": 4, "value": 4}, {"hours_from_onset": 7, "value": 4}],
        "history": {"previous_visits": []},
        "default_label": "musculoskeletal chest pain",
    },
}

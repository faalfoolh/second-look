"""Load PTB-XL ECGs and measure ST deviation per lead.

Measurements are approximate (fixed offsets from the R peak) and are for
demonstration only, not diagnosis.
"""
from pathlib import Path

import numpy as np
import wfdb
from scipy.signal import butter, filtfilt, find_peaks

DATA_DIR = Path(__file__).parent / "data"

LEADS = ["I", "II", "III", "AVR", "AVL", "AVF", "V1", "V2", "V3", "V4", "V5", "V6"]

# Anatomically contiguous lead groups used by STEMI criteria
GROUPS = {
    "inferior": ["II", "III", "AVF"],
    "anterior": ["V1", "V2", "V3", "V4"],
    "lateral": ["I", "AVL", "V5", "V6"],
}

SUBTLE_MV = 0.05  # 0.5 mm: worth a second look, below STEMI thresholds
SUBTLE_V1_V3_MARGIN = 0.05  # V1-V3 often show normal ST elevation, so the band sits just under the threshold
DEPRESSION_MV = 0.10  # 1 mm


def load(record_id):
    rec = wfdb.rdrecord(str(DATA_DIR / record_id))
    names = [n.upper() for n in rec.sig_name]
    return rec.p_signal, rec.fs, names


def _filter(sig, fs):
    # 0.05 Hz high-pass keeps the ST segment intact; 40 Hz low-pass removes noise
    b, a = butter(2, [0.05 / (fs / 2), 40 / (fs / 2)], btype="band")
    return filtfilt(b, a, sig, axis=0)


def r_peaks(lead, fs):
    """Simple Pan-Tompkins style detector: derivative, square, integrate, peak-pick."""
    b, a = butter(2, [5 / (fs / 2), 15 / (fs / 2)], btype="band")
    x = filtfilt(b, a, lead)
    energy = np.convolve(np.diff(x) ** 2, np.ones(int(0.15 * fs)) / (0.15 * fs), mode="same")
    peaks, _ = find_peaks(energy, height=0.3 * energy.max(), distance=int(0.3 * fs))
    # Snap each energy peak to the largest absolute deflection nearby
    win = int(0.08 * fs)
    return np.array([p - win + np.argmax(np.abs(lead[max(p - win, 0):p + win])) for p in peaks if p > win])


def st_deviation(signals, fs, names):
    """Median ST deviation (mV) per lead: point at R+100 ms minus PR baseline at R-80 ms."""
    sig = _filter(signals, fs)
    peaks = r_peaks(sig[:, names.index("II")], fs)
    peaks = peaks[(peaks > int(0.1 * fs)) & (peaks < len(sig) - int(0.12 * fs))]
    if len(peaks) < 3:
        raise ValueError(f"Only {len(peaks)} beats detected in lead II; ST measurement needs at least 3")
    st, base = peaks + int(0.10 * fs), peaks - int(0.08 * fs)
    return {name: float(np.median(sig[st, i] - sig[base, i])) for i, name in enumerate(names)}, peaks


def stemi_threshold(lead, sex, age):
    """4th Universal Definition of MI: V2-V3 thresholds depend on sex and age."""
    if lead in ("V2", "V3"):
        if sex == "F":
            return 0.15
        return 0.25 if age < 40 else 0.20
    return 0.10


def subtle_floor(lead, sex, age):
    if lead in ("V1", "V2", "V3"):
        return stemi_threshold(lead, sex, age) - SUBTLE_V1_V3_MARGIN
    return SUBTLE_MV


def interpret(st, sex, age):
    """Find contiguous-lead patterns: STEMI-level, subtle elevation, or depression."""
    findings = []
    for group, leads in GROUPS.items():
        meets = [l for l in leads if st[l] >= stemi_threshold(l, sex, age)]
        subtle = [l for l in leads if subtle_floor(l, sex, age) <= st[l] < stemi_threshold(l, sex, age)]
        depressed = [l for l in leads if st[l] <= -DEPRESSION_MV]
        if len(meets) >= 2:
            findings.append(("stemi", group, meets))
        elif len(meets) + len(subtle) >= 2:
            findings.append(("subtle", group, meets + subtle))
        if len(depressed) >= 2:
            findings.append(("depression", group, depressed))
    return findings

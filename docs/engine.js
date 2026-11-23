// Second Look rules engine for the browser.
// A line-for-line port of rules.py and ecg.interpret(). Thresholds, phrases and
// references come from data.json (exported from Python), and
// tests/test_web_parity.py checks this file against the Python engine.

const PRETTY = { AVR: "aVR", AVL: "aVL", AVF: "aVF" };
export const pretty = (leads) => leads.map((l) => PRETTY[l] ?? l);

const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export function makeEngine(R) {
  const patterns = Object.fromEntries(
    Object.entries(R.symptom_phrases).map(([sym, phrases]) => [
      sym,
      phrases.map((ph) => ({ ph, re: new RegExp("\\b" + escapeRe(ph) + (ph.length <= 4 ? "\\b" : "")) })),
    ]),
  );
  const negations = new RegExp(R.negations);
  const cardiac = new Set(R.cardiac_symptoms);
  const nonCardiac = new Set(R.non_cardiac_labels);

  // Returns recognised symptoms plus the negated phrases it skipped (for display)
  function readNote(note) {
    const found = new Set();
    const negated = [];
    for (const clause of note.toLowerCase().split(/[.,;:\n]|\bbut\b/)) {
      for (const [sym, list] of Object.entries(patterns)) {
        for (const { ph, re } of list) {
          const m = re.exec(clause);
          if (!m) continue;
          if (ph.startsWith("no ") || !negations.test(clause.slice(0, m.index))) {
            found.add(sym);
            break;
          }
          negated.push({ sym, text: clause.slice(0, m.index + ph.length).trim() });
        }
      }
    }
    const kept = negated.filter((n) => !found.has(n.sym));
    return { symptoms: [...found].sort(), negated: kept.filter((n, i) => kept.findIndex((k) => k.sym === n.sym) === i) };
  }
  const extractSymptoms = (note) => readNote(note).symptoms;

  const finding = (level, text, action = "", ref = "") => ({ level, text, action, ref });
  const troponinLimit = (sex) => R.troponin_url[sex] ?? Math.min(...Object.values(R.troponin_url));

  function checkTroponin(p) {
    const tests = p.troponin;
    if (!tests.length) return finding("red", "No troponin taken.", "Order troponin", R.refs.troponin);
    const url = troponinLimit(p.sex);
    const first = tests[0].value;
    const last = tests[tests.length - 1].value;
    if (tests.length > 1 && last - first >= R.rising_delta)
      return finding("red", `Troponin rising: ${first} → ${last} ng/L.`, "Refer to cardiology", R.refs.troponin);
    const high = tests.map((t) => t.value).filter((v) => v > url);
    if (high.length) {
      const who = p.sex === "F" ? "women" : "men";
      return finding("red", `Troponin ${Math.max(...high)} ng/L is above the upper limit for ${who} (${url} ng/L).`,
        "Refer to cardiology", R.refs.troponin_sex);
    }
    if (tests.length === 1) {
      const t = tests[0];
      if (t.value < R.very_low_troponin && t.hours_from_onset >= R.min_hours_for_single_test) return null;
      const why = t.hours_from_onset < R.min_hours_for_single_test
        ? `Normal result, but taken only ${t.hours_from_onset} h after symptoms began: too early to rule out a heart attack. Troponin can take hours to rise.`
        : "Not low enough to rule out a heart attack on a single test.";
      return finding("amber", `Only one troponin (${t.value} ng/L, ${t.hours_from_onset} h after onset). ${why}`,
        "Order repeat troponin", R.refs.troponin);
    }
    return null;
  }

  function checkEcg(ecgFindings) {
    if (ecgFindings === null) return [finding("red", "No ECG recorded.", "Do a 12-lead ECG now", R.refs.no_ecg)];
    const out = [];
    for (const [kind, group, leads] of ecgFindings) {
      const txt = pretty(leads).join(", ");
      if (kind === "stemi")
        out.push(finding("red", `ECG meets STEMI criteria in ${group} leads (${txt}).`, "Activate cath lab pathway", R.refs.ecg));
      else if (kind === "subtle")
        out.push(finding("amber", `Subtle ST elevation in ${group} leads (${txt}), below STEMI thresholds.`, "Senior ECG review", R.refs.ecg_subtle));
      else if (kind === "depression")
        out.push(finding("amber", `ST depression in ${group} leads (${txt}).`, "Senior ECG review", R.refs.ecg));
    }
    return out;
  }

  function checkHistory(p) {
    const h = p.history;
    if (h === null || h === undefined) return [[], R.history_questions];
    const out = [];
    if (p.sex === "F") {
      if (h.months_since_pregnancy !== undefined && h.months_since_pregnancy !== null && h.months_since_pregnancy <= 12)
        out.push(finding("red",
          `Pregnant or gave birth ${h.months_since_pregnancy} months ago: consider SCAD (spontaneous coronary artery dissection) even with normal tests.`,
          "Senior review", R.refs.scad));
      for (const [key, text] of R.women_risk_factors)
        if (h[key]) out.push(finding("amber", text, "", key === "early_menopause" ? R.refs.menopause : R.refs.pregnancy_risk));
    }
    for (const [key, text] of R.general_risk_factors) if (h[key]) out.push(finding("amber", text, "", R.refs.diabetes));
    const visits = (h.previous_visits ?? []).filter((v) => v.months_ago <= R.repeat_window_months);
    if (visits.length)
      out.push(finding("amber",
        `${visits.length} previous A&E visit(s) with similar symptoms in the last ${R.repeat_window_months} months.`, "", R.refs.repeat));
    return [out, []];
  }

  function levelOf(findings, questions) {
    if (findings.some((f) => f.level === "red")) return "red";
    return findings.length || questions.length ? "amber" : "clear";
  }

  // Main entry point: run at the moment of discharge
  function secondLook(p, label, ecgFindings) {
    if (!nonCardiac.has(label) || !p.symptoms.some((s) => cardiac.has(s)))
      return { triggered: false, level: "clear", findings: [], questions: [] };
    const findings = [];
    const trop = checkTroponin(p);
    if (trop) findings.push(trop);
    findings.push(...checkEcg(ecgFindings));
    const [historyFindings, questions] = checkHistory(p);
    // Risk factors only matter when something in the work-up is also outstanding
    if (findings.length || questions.length) findings.push(...historyFindings);
    else findings.push(...historyFindings.filter((f) => f.level === "red"));
    return { triggered: true, level: levelOf(findings, questions), findings, questions };
  }

  // ECG: STEMI thresholds (4th Universal Definition of MI) and contiguous-lead patterns
  const E = R.ecg;
  function stemiThreshold(lead, sex, age) {
    if (lead === "V2" || lead === "V3") return sex === "F" ? 0.15 : age < 40 ? 0.25 : 0.2;
    return 0.1;
  }
  function subtleFloor(lead, sex, age) {
    return ["V1", "V2", "V3"].includes(lead) ? stemiThreshold(lead, sex, age) - E.subtle_v1_v3_margin : E.subtle_mv;
  }
  function interpret(st, sex, age) {
    const out = [];
    for (const [group, leads] of Object.entries(E.groups)) {
      const meets = leads.filter((l) => st[l] >= stemiThreshold(l, sex, age));
      const subtle = leads.filter((l) => subtleFloor(l, sex, age) <= st[l] && st[l] < stemiThreshold(l, sex, age));
      const depressed = leads.filter((l) => st[l] <= -E.depression_mv);
      if (meets.length >= 2) out.push(["stemi", group, meets]);
      else if (meets.length + subtle.length >= 2) out.push(["subtle", group, [...meets, ...subtle]]);
      if (depressed.length >= 2) out.push(["depression", group, depressed]);
    }
    return out;
  }

  return { readNote, extractSymptoms, secondLook, interpret, stemiThreshold, subtleFloor, troponinLimit };
}

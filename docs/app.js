import { makeEngine, pretty } from "./engine.js";

const data = await (await fetch("data/data.json")).json();
const R = data.rules;
const eng = makeEngine(R);
const PATIENTS = data.patients;
const RECORDS = data.records;
const NAMES = Object.keys(PATIENTS);

// One-line summaries for the board (display only)
const COMPLAINT = {
  "Sarah, 44": "Chest pain, breathless, very anxious",
  "Emma, 52": "Burning chest after a large meal",
  "Aisha, 38": "Breathless and nauseous, no records here",
  "Linda, 61": "Upper stomach pain, nausea, back ache",
  "James, 48": "Chest pain after lifting at the gym",
};
// Column-major: the grid flows down each column (limb leads, then chest leads)
const ROW_ORDER = ["I", "II", "III", "AVR", "AVL", "AVF", "V1", "V2", "V3", "V4", "V5", "V6"];
const ANYWAY_REASONS = ["Senior reviewed and agreed", "Patient declined further tests", "Clear alternative diagnosis"];

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const clone = (x) => (x === null || x === undefined ? x : JSON.parse(JSON.stringify(x)));
const first = (name) => name.split(",")[0];
const fmt = (v) => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(2);

// ---------------------------------------------------------------- state
let current = NAMES[0];
let states = {};
let audit = [];

function freshState(name) {
  const p = PATIENTS[name];
  return {
    note: p.triage_note, label: p.default_label, history: clone(p.history), ecg: p.ecg,
    troponin: clone(p.troponin), ordersUsed: 0, stage: "assess", answers: [false, false, false, false],
    logged: false, outcome: null, anyway: "", showPoints: false,
  };
}
function resetAll() {
  states = Object.fromEntries(NAMES.map((n) => [n, freshState(n)]));
  audit = [];
}
resetAll();

function log(name, event, kind = "action") {
  const t = new Date();
  audit.push({ time: t.toTimeString().slice(0, 8), patient: name, event, kind });
}

// ---------------------------------------------------------------- engine glue
function ecgFindings(name) {
  const s = states[name];
  if (!s.ecg) return null;
  const p = PATIENTS[name];
  return eng.interpret(RECORDS[s.ecg].st_mv, p.sex, p.age);
}
function evaluate(name) {
  const p = PATIENTS[name];
  const s = states[name];
  const now = { ...p, history: s.history, symptoms: eng.extractSymptoms(s.note), troponin: s.troponin };
  const findings = ecgFindings(name);
  return { result: eng.secondLook(now, s.label, findings), findings };
}
function headlineOf(result) {
  if (result.findings.some((f) => f.text.startsWith("Troponin rising"))) return "Heart attack (NSTEMI) likely: do not discharge.";
  if (result.level === "red") return "A heart attack has not been ruled out: urgent senior review.";
  return "A heart attack (NSTEMI) has not been ruled out.";
}
function status(name) {
  const s = states[name];
  if (s.stage !== "checked") return { cls: "", text: "Not yet checked" };
  if (s.outcome?.kind === "anyway") return { cls: "amber", text: "Discharged despite alert" };
  if (s.outcome?.kind === "senior") return { cls: "amber", text: "Senior review" };
  const { result } = evaluate(name);
  if (!result.triggered || result.level === "clear") return { cls: "green", text: "Cleared to go home" };
  return result.level === "red" ? { cls: "red", text: "Stopped: urgent" } : { cls: "amber", text: "Stopped: work-up incomplete" };
}

// ---------------------------------------------------------------- board
function renderBoard() {
  document.getElementById("patients").innerHTML = NAMES.map((n) => {
    const p = PATIENTS[n];
    const st = status(n);
    return `<button class="card" role="tab" aria-selected="${n === current}" data-patient="${esc(n)}">
      <span class="card-name">${esc(first(n))}</span>
      <span class="card-meta">${p.sex === "F" ? "Female" : "Male"} · ${p.age} y</span>
      <span class="card-complaint">${esc(COMPLAINT[n] ?? "")}</span>
      <span class="pill ${st.cls}">${st.text}</span>
    </button>`;
  }).join("");
}

// ---------------------------------------------------------------- troponin chart
function troponinChart(p, tests) {
  const W = 340, H = 170, L = 34, B = 26, T = 14, Rr = 12;
  const limit = eng.troponinLimit(p.sex);
  const maxH = Math.max(8, ...tests.map((t) => t.hours_from_onset + 1));
  const maxV = Math.max(limit * 2.6, ...tests.map((t) => t.value * 1.25));
  const x = (h) => L + (h / maxH) * (W - L - Rr);
  const y = (v) => T + (1 - v / maxV) * (H - T - B);
  const pts = tests.map((t) => [x(t.hours_from_onset), y(t.value), t]);
  const ticks = [0, 2, 4, 6, 8].filter((h) => h <= maxH);
  return `<svg class="trop-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Troponin results against the ${p.sex === "F" ? "female" : "male"} upper limit">
    <line x1="${L}" x2="${W - Rr}" y1="${y(0)}" y2="${y(0)}" stroke="var(--line)"/>
    ${ticks.map((h) => `<text x="${x(h)}" y="${H - 8}" text-anchor="middle">${h} h</text>`).join("")}
    <line x1="${L}" x2="${W - Rr}" y1="${y(limit)}" y2="${y(limit)}" stroke="var(--red)" stroke-dasharray="4 3"/>
    <text x="${W - Rr}" y="${y(limit) - 5}" text-anchor="end" fill="var(--red)">upper limit, ${p.sex === "F" ? "women" : "men"}: ${limit} ng/L</text>
    <line x1="${x(R.min_hours_for_single_test)}" x2="${x(R.min_hours_for_single_test)}" y1="${T}" y2="${y(0)}" stroke="var(--line)" stroke-dasharray="2 3"/>
    <text x="${x(R.min_hours_for_single_test) + 4}" y="${T + 8}">3 h</text>
    ${pts.length > 1 ? `<polyline points="${pts.map(([a, b]) => `${a},${b}`).join(" ")}" fill="none" stroke="var(--ink)" stroke-width="1.5"/>` : ""}
    ${pts.map(([a, b, t]) => `<circle cx="${a}" cy="${b}" r="4.5" fill="${t.value > limit ? "var(--red)" : "var(--ink)"}"/>
      <text class="val" x="${a}" y="${b - 9}" text-anchor="middle">${t.value}</text>`).join("")}
    <text x="4" y="${T + 4}">ng/L</text>
  </svg>`;
}

// ---------------------------------------------------------------- ECG drawing
function gridDefs() {
  return `<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
    <pattern id="ecg-grid" width="5" height="5" patternUnits="userSpaceOnUse">
      ${[1, 2, 3, 4].map((i) => `<line x1="${i}" x2="${i}" y1="0" y2="5" stroke="var(--ecg-minor)" stroke-width="0.08"/><line y1="${i}" y2="${i}" x1="0" x2="5" stroke="var(--ecg-minor)" stroke-width="0.08"/>`).join("")}
      <path d="M0 0H5M0 0V5" stroke="var(--ecg-major)" stroke-width="0.2"/>
    </pattern></defs></svg>`;
}

// 25 mm/s and 10 mm/mV, drawn in millimetres
function trace(uv, fs, hi) {
  let d = "";
  for (let i = 0; i < uv.length; i++) d += `${i ? "L" : "M"}${((i / fs) * 25).toFixed(2)} ${((hi - uv[i] / 1000) * 10).toFixed(2)}`;
  return d;
}
function sampleAt(uv, fs, t) {
  const i = Math.min(uv.length - 1, Math.max(0, Math.round(t * fs)));
  return uv[i] / 1000;
}
function markers(rec, uv, start, len, hi) {
  const E = R.ecg;
  let out = "";
  for (const r of rec.r_peaks_s) {
    const tb = r + E.baseline_offset_s - start, ts = r + E.st_offset_s - start;
    if (tb < 0 || ts > len) continue;
    const vb = sampleAt(uv, rec.fs, tb), vs = sampleAt(uv, rec.fs, ts);
    const X = (t) => (t * 25).toFixed(2), Y = (v) => ((hi - v) * 10).toFixed(2);
    out += `<line x1="${X(tb)}" x2="${X(ts)}" y1="${Y(vb)}" y2="${Y(vb)}" stroke="var(--base-pt)" stroke-dasharray="1 1" stroke-width="0.25"/>
      <line x1="${X(ts)}" x2="${X(ts)}" y1="${Y(vb)}" y2="${Y(vs)}" stroke="var(--flag)" stroke-width="0.45"/>
      <circle cx="${X(tb)}" cy="${Y(vb)}" r="0.7" fill="var(--base-pt)"/>
      <circle cx="${X(ts)}" cy="${Y(vs)}" r="0.7" fill="var(--flag)"/>`;
  }
  return out;
}
function ecgPanel(rec, lead, flagged, showPoints, p) {
  const [lo, hi] = rec.range_mv;
  const L = rec.leads[lead];
  const w = 62.5, h = (hi - lo) * 10;
  const st = rec.st_mv[lead];
  const thr = eng.stemiThreshold(lead, p.sex, p.age);
  const name = pretty([lead])[0];
  const isFlag = flagged.has(lead);
  return `<div class="ecg-panel${isFlag ? " flag" : ""}">
    <span class="lead">${name}</span>${showPoints ? `<span class="stval">ST ${fmt(st)}</span>` : ""}
    <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Lead ${name}, ST ${fmt(st)} millivolts">
      <title>${name}: ST ${fmt(st)} mV · STEMI threshold ${thr.toFixed(2)} mV${isFlag ? " · flagged" : ""}</title>
      <rect width="${w}" height="${h}" fill="url(#ecg-grid)"/>
      <path d="${trace(L.uv, rec.fs, hi)}" fill="none" stroke="${isFlag ? "var(--flag)" : "var(--trace)"}" stroke-width="1.3" vector-effect="non-scaling-stroke" stroke-linejoin="round"/>
      ${showPoints ? markers(rec, L.uv, L.start_s, 2.5, hi) : ""}
    </svg></div>`;
}
function rhythmStrip(rec, showPoints) {
  const [lo, hi] = rec.range_mv;
  const w = 250, h = (hi - lo) * 10;
  const peaks = showPoints ? rec.r_peaks_s.map((r) => `<path d="M${(r * 25).toFixed(2)} 1.2l-1.2 -1.2h2.4z" fill="var(--accent)"/>`).join("") : "";
  return `<div class="rhythm"><span class="lead">II · 10 s rhythm strip</span>
    <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Lead II rhythm strip, 10 seconds">
      <rect width="${w}" height="${h}" fill="url(#ecg-grid)"/>
      <path d="${trace(rec.rhythm_ii, rec.fs, hi)}" fill="none" stroke="var(--trace)" stroke-width="1.2" vector-effect="non-scaling-stroke"/>
      ${peaks}
    </svg></div>`;
}
function ecgBlock(name) {
  const p = PATIENTS[name], s = states[name];
  if (!s.ecg) {
    return `<div class="ecg-head"><h3>12-lead ECG</h3></div>
      <div class="empty">No ECG recorded for this visit.${p.ecg_if_done ? " Second Look will ask for one." : ""}</div>`;
  }
  const rec = RECORDS[s.ecg];
  const findings = ecgFindings(name);
  const flagged = new Set(findings.flatMap(([, , leads]) => leads));
  return `<div class="ecg-head">
      <div><h3>12-lead ECG</h3><p class="muted small">${esc(p.ecg_note)}. 25 mm/s, 10 mm/mV, filtered 0.05–40 Hz.</p></div>
      <label class="toggle"><input type="checkbox" data-act="points" ${s.showPoints ? "checked" : ""}> Show measurement points</label>
    </div>
    <div class="ecg">${ROW_ORDER.map((l) => ecgPanel(rec, l, flagged, s.showPoints, p)).join("")}</div>
    ${rhythmStrip(rec, s.showPoints)}
    <div class="legend">
      <span><i style="background:var(--flag)"></i>Leads flagged by Second Look</span>
      ${s.showPoints ? `<span><i style="background:var(--base-pt)"></i>PR baseline (R − 80 ms)</span><span><i style="background:var(--flag)"></i>ST point (R + 100 ms)</span><span><i style="background:var(--accent);border-radius:0"></i>Detected R peaks</span>` : `<span>Hover a lead for its ST value</span>`}
    </div>
    <details class="st-table"><summary>ST deviation in every lead (median across ${rec.r_peaks_s.length} beats)</summary>
      <div class="st-grid">${ROW_ORDER.map((l) => `<div class="st-cell${flagged.has(l) ? " flag" : ""}"><b>${pretty([l])[0]}</b>${fmt(rec.st_mv[l])} mV</div>`).join("")}</div>
    </details>`;
}

// ---------------------------------------------------------------- case sections
function chipsHTML(note) {
  const { symptoms, negated } = eng.readNote(note);
  const on = symptoms.map((s) => `<span class="chip">${esc(s)}</span>`).join("");
  const off = negated.map((n) => `<span class="chip neg" title="Negated in the note">${esc(n.sym)}</span>`).join("");
  return on || off ? on + off : `<span class="chip none">No heart-type symptoms recognised</span>`;
}
function historyHTML(p, h) {
  if (h === null || h === undefined) return `<div class="empty">No medical record available for this patient.</div>`;
  const items = [];
  if (h.months_since_pregnancy !== undefined && h.months_since_pregnancy !== null) items.push(`Gave birth ${h.months_since_pregnancy} months ago`);
  for (const [k, text] of [...R.women_risk_factors, ...R.general_risk_factors]) if (h[k]) items.push(text.split(":")[0]);
  items.push(`Previous similar A&E visits: ${(h.previous_visits ?? []).length}`);
  return `<ul class="facts-list">${items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>`;
}

function compareHTML(name, result, findings, headline) {
  const p = PATIENTS[name], s = states[name];
  const rising = result.findings.some((f) => f.text.startsWith("Troponin rising"));
  const tests = rising ? s.troponin : s.troponin.slice(0, 1);
  const doc = [], sl = [];
  if (findings === null) {
    doc.push(["", "<b>ECG:</b> not done"]);
    sl.push(["bad", "<b>ECG:</b> not done"]);
  } else if (!findings.length) {
    doc.push(["ok", "<b>ECG:</b> no ST elevation"]);
    sl.push(["warn", "<b>ECG:</b> all 12 leads analysed, no ST elevation. A heart attack without ST elevation (NSTEMI) cannot be ruled out by ECG."]);
  } else {
    const leads = [...new Set(findings.flatMap(([, , ls]) => pretty(ls)))].join(", ");
    const stemi = findings.some(([k]) => k === "stemi");
    doc.push(["ok", "<b>ECG:</b> nothing clearly worrying"]);
    sl.push([stemi ? "bad" : "warn", stemi ? `<b>ECG:</b> meets STEMI criteria (${leads})` : `<b>ECG:</b> subtle ST changes in ${leads}, below STEMI thresholds`]);
  }
  if (tests.length) {
    const t = tests[0];
    const ok = t.value <= eng.troponinLimit(p.sex);
    doc.push([ok ? "ok" : "bad", `<b>Troponin:</b> ${t.value} ng/L, ${ok ? "below" : "above"} threshold`]);
    const tf = result.findings.find((f) => f.text.toLowerCase().includes("troponin"));
    if (!tf) sl.push(["ok", `<b>Troponin:</b> ${t.value} ng/L, valid rule-out`]);
    else if (tf.text.startsWith("Only one") && t.hours_from_onset < R.min_hours_for_single_test)
      sl.push(["warn", `<b>Troponin:</b> ${t.value} ng/L is normal, but taken only ${t.hours_from_onset} h after symptoms began: too early to rule out`]);
    else sl.push([tf.level === "red" ? "bad" : "warn", `<b>Troponin:</b> ${esc(tf.text)}`]);
  } else {
    doc.push(["", "<b>Troponin:</b> not done"]);
    sl.push(["bad", "<b>Troponin:</b> not done"]);
  }
  doc.push(["", `<b>Impression:</b> ${esc(s.label)}`]);
  const keys = ["pre-eclampsia", "pregnancy", "Pregnant", "menopause", "diabetes", "previous A&E"];
  const risks = result.findings.filter((f) => keys.some((k) => f.text.includes(k))).map((f) => f.text.split(":")[0]);
  sl.push(risks.length ? ["warn", `<b>History:</b> ${esc(risks.join(" · "))}`]
    : s.history === null || s.history === undefined ? ["warn", "<b>History:</b> no record: ask the patient"] : ["ok", "<b>History:</b> nothing relevant"]);
  const MARK = { ok: "✓", warn: "!", bad: "✕", "": "·" };
  const li = ([m, t]) => `<li><span class="mark ${m}">${MARK[m]}</span><span>${t}</span></li>`;
  return `<div class="compare">
    <div><h4>What the doctor sees</h4><ul>${doc.map(li).join("")}</ul><div class="final">Verdict: send home</div></div>
    <div class="sl"><h4>What Second Look sees</h4><ul>${sl.map(li).join("")}</ul><div class="final">Verdict: ${esc(headline)}</div></div>
  </div>`;
}

function phoneHTML(name) {
  return `<div class="phone"><div class="from">Text message · NHS A&amp;E</div><div class="bubble">Hi ${esc(first(name))}. ${esc(R.safety_net_message)}</div></div>`;
}
function timelineHTML(p) {
  if (!p.timeline_without) return "";
  const col = (cls, title, rows) => `<div class="${cls}"><h4>${title}</h4><ol>${rows.map(([w, t]) => `<li><b>${esc(w)}</b>${esc(t)}</li>`).join("")}</ol></div>`;
  return `<div><h3>Why it matters</h3><div class="timeline">${col("bad", "Without Second Look", p.timeline_without)}${col("good", "With Second Look", p.timeline_with)}</div></div>`;
}

function slHTML(name) {
  const p = PATIENTS[name], s = states[name];
  if (s.stage !== "checked") return "";
  const { result, findings } = evaluate(name);
  const symptoms = eng.extractSymptoms(s.note);
  const head = `<div class="step-title"><span class="num">§ 05</span><h3>Second Look</h3></div>`;

  if (!result.triggered || result.level === "clear") {
    const why = !result.triggered
      ? (R.non_cardiac_labels.includes(s.label) ? "No heart-type symptoms in the triage note, so there was nothing to check." : "The diagnosis is cardiac, so Second Look does not need to step in.")
      : "Troponin, ECG and history are complete and normal.";
    return `${head}<div class="verdict green"><div class="icon">✓</div><div><h4>Discharged. No gaps in the work-up.</h4><p>${why} Second Look stays silent.</p></div></div>
      ${symptoms.length ? `<div class="outcome">${phoneHTML(name)}<div><h3>Safety-net message</h3><p class="muted">Every patient with heart-type symptoms gets this text on discharge, so she knows which symptoms mean she should come straight back.</p></div></div>` : ""}`;
  }

  const headline = headlineOf(result);
  const orders = p.troponin_orders ?? [];
  const canOrder = s.ordersUsed < orders.length;
  const tropLabel = s.troponin.length ? "Order repeat troponin" : "Order troponin";
  const questions = result.questions.length ? `<div class="questions"><h4>No history available. Ask ${esc(first(name))}:</h4>
      ${result.questions.map((q, i) => `<label><input type="checkbox" data-q="${i}" ${s.answers[i] ? "checked" : ""}> ${esc(q)}</label>`).join("")}
      <div style="margin-top:10px"><button class="btn" data-act="record">Update record</button></div></div>` : "";
  let outcome = "";
  if (s.outcome?.kind === "senior") outcome = `<div class="note">Senior review requested at ${s.outcome.time}. ${esc(first(name))} stays in A&amp;E.</div>`;
  if (s.outcome?.kind === "anyway") outcome = `<div class="outcome">${phoneHTML(name)}<div><h3>Discharged with a recorded reason</h3><p>Reason: <b>${esc(s.outcome.reason)}</b>. The override is logged in the hospital report.</p></div></div>`;

  return `${head}
    <div class="verdict ${result.level}"><div class="icon">!</div><div><h4>Before you discharge ${esc(first(name))}</h4><p>${esc(headline)}</p></div></div>
    ${compareHTML(name, result, findings, headline)}
    <h3>What is outstanding</h3>
    <ul class="findings">${result.findings.map((f) => `<li class="finding ${f.level}">${esc(f.text)}
      ${f.action ? `<br><span class="next">Next step → ${esc(f.action)}</span>` : ""}
      ${f.ref ? `<span class="ref">${esc(f.ref)}</span>` : ""}</li>`).join("")}</ul>
    ${questions}
    <div class="actions">
      ${!s.ecg && p.ecg_if_done ? `<button class="btn btn-primary" data-act="ecg">Do ECG now</button>` : ""}
      <button class="btn${canOrder ? " btn-primary" : ""}" data-act="trop" ${canOrder ? "" : "disabled"}>${tropLabel}</button>
      <button class="btn" data-act="senior">Request senior review</button>
      <span class="sep"></span>
      <span class="anyway"><select data-act="reason" aria-label="Reason to discharge anyway"><option value="">Discharge anyway: reason…</option>
        ${ANYWAY_REASONS.map((r) => `<option ${s.anyway === r ? "selected" : ""}>${esc(r)}</option>`).join("")}</select>
        <button class="btn" data-act="anyway" ${s.anyway ? "" : "disabled"}>Confirm</button></span>
    </div>
    ${outcome}
    ${timelineHTML(p) ? `<div style="margin-top:32px">${timelineHTML(p)}</div>` : ""}`;
}

function renderCase() {
  const name = current, p = PATIENTS[name], s = states[name];
  const labels = [...R.non_cardiac_labels, ...R.other_labels];
  document.getElementById("case").innerHTML = `${gridDefs()}
  <article class="dossier">
    <div class="dossier-head">
      <div><p class="kicker">Patient file</p><h2>${esc(first(name))}, ${p.age}</h2><p class="story">${esc(p.story)}</p></div>
      <div class="meta-grid"><span>Sex</span><b>${p.sex === "F" ? "Female" : "Male"}</b><span>Age</span><b>${p.age}</b>
        <span>Record</span><b>${s.history === null || s.history === undefined ? "none" : "available"}</b><span>Status</span><b>${status(name).text}</b></div>
    </div>
    <section class="step">
      <div class="step-title"><span class="num">§ 01</span><h3>Triage</h3></div>
      <label class="field" for="note">Triage note (free text: try editing it)</label>
      <textarea id="note" rows="3">${esc(s.note)}</textarea>
      <div class="chips" id="chips">${chipsHTML(s.note)}</div>
      <p class="hint">Recognised heart-type symptoms. Struck-through ones were negated in the note ("no chest pain").</p>
    </section>
    <section class="step">
      <div class="step-title"><span class="num">§ 02</span><h3>Tests</h3></div>
      <div class="grid-2">
        <div><h3>Troponin (hs-cTn)</h3>${s.troponin.length ? troponinChart(p, s.troponin) : `<div class="empty">No troponin taken.</div>`}</div>
        <div><h3>Results</h3>${s.troponin.length ? `<table><thead><tr><th>Hours after onset</th><th>Result</th></tr></thead><tbody>
          ${s.troponin.map((t) => `<tr><td class="num">${t.hours_from_onset} h</td><td class="num">${t.value} ng/L</td></tr>`).join("")}</tbody></table>` : ""}
          <p class="muted small" style="margin-top:12px">The upper limit is sex-specific: ${R.troponin_url.F} ng/L for women and ${R.troponin_url.M} ng/L for men (placeholder values for one assay).</p></div>
      </div>
      <div id="ecg-block">${ecgBlock(name)}</div>
    </section>
    <section class="step">
      <div class="step-title"><span class="num">§ 03</span><h3>History</h3></div>
      ${historyHTML(p, s.history)}
    </section>
    <section class="step">
      <div class="step-title"><span class="num">§ 04</span><h3>Discharge</h3></div>
      <div class="discharge">
        <div class="grow"><label class="field" for="label">Discharge diagnosis</label>
          <select id="label">${labels.map((l) => `<option ${l === s.label ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></div>
        <button class="btn btn-primary" data-act="discharge">Discharge patient</button>
      </div>
    </section>
    <section class="step" id="sl-section" ${s.stage === "checked" ? "" : "hidden"}>${slHTML(name)}</section>
  </article>`;
}

function renderReport() {
  const n = (k) => audit.filter((e) => e.kind === k).length;
  document.getElementById("report-body").innerHTML = `<div class="metrics">
      <div class="metric"><b>${n("attempt")}</b><span>Discharges checked</span></div>
      <div class="metric"><b>${n("fired")}</b><span>Second Look stepped in</span></div>
      <div class="metric"><b>${n("silent")}</b><span>Stayed silent</span></div></div>
    <div class="log">${audit.length ? `<table><thead><tr><th>Time</th><th>Patient</th><th>Event</th></tr></thead><tbody>
      ${[...audit].reverse().map((e) => `<tr><td class="num">${e.time}</td><td>${esc(e.patient)}</td><td>${esc(e.event)}</td></tr>`).join("")}</tbody></table>`
      : `<p class="muted" style="padding:16px 20px;margin:0">Nothing yet. Open a patient above and press <b>Discharge patient</b>.</p>`}</div>`;
}

function renderValidation() {
  const rows = Object.entries(RECORDS).map(([, r]) => {
    const f = eng.interpret(r.st_mv, r.sex, r.age);
    const txt = f.length ? f.map(([k, g, ls]) => `${k === "stemi" ? "STEMI criteria" : k === "subtle" ? "Subtle elevation" : "ST depression"} ${pretty(ls).join(", ")}`).join("; ") : "None";
    return `<tr><td class="num">${r.ptbxl_id}</td><td>${r.sex === "F" ? "Woman" : "Man"}, ${r.age}</td><td>${esc(r.label)}</td><td>${esc(txt)}</td></tr>`;
  });
  document.getElementById("validation").innerHTML = `<table><thead><tr><th>PTB-XL</th><th>Patient</th><th>Label</th><th>Second Look finding</th></tr></thead><tbody>${rows.join("")}</tbody></table>`;
}

function renderAll() {
  renderBoard();
  renderCase();
  renderReport();
}
function refreshLive() {
  // Update everything that depends on the note or label without touching the text box
  document.getElementById("chips").innerHTML = chipsHTML(states[current].note);
  const sec = document.getElementById("sl-section");
  sec.innerHTML = slHTML(current);
  renderBoard();
}

// ---------------------------------------------------------------- events
document.getElementById("patients").addEventListener("click", (e) => {
  const card = e.target.closest("[data-patient]");
  if (!card) return;
  current = card.dataset.patient;
  renderAll();
  document.getElementById("case").scrollIntoView({ behavior: "smooth", block: "start" });
});
document.getElementById("reset").addEventListener("click", () => { resetAll(); renderAll(); });

const caseEl = document.getElementById("case");
caseEl.addEventListener("input", (e) => {
  if (e.target.id === "note") { states[current].note = e.target.value; refreshLive(); }
});
caseEl.addEventListener("change", (e) => {
  const s = states[current];
  if (e.target.id === "label") { s.label = e.target.value; refreshLive(); }
  else if (e.target.dataset.act === "points") { s.showPoints = e.target.checked; document.getElementById("ecg-block").innerHTML = ecgBlock(current); }
  else if (e.target.dataset.q !== undefined) s.answers[+e.target.dataset.q] = e.target.checked;
  else if (e.target.dataset.act === "reason") { s.anyway = e.target.value; refreshLive(); }
});
caseEl.addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-act]");
  if (!btn || btn.disabled) return;
  const name = current, p = PATIENTS[name], s = states[name];
  const act = btn.dataset.act;
  if (act === "discharge") {
    s.stage = "checked"; s.outcome = null; s.logged = false;
    log(name, `Discharge attempted: ${s.label}`, "attempt");
    const { result } = evaluate(name);
    if (!result.triggered || result.level === "clear") log(name, "Second Look silent: discharged", "silent");
    else log(name, `Second Look stepped in (${result.findings.length + result.questions.length} items)`, "fired");
    s.logged = true;
    renderAll();
    document.getElementById("sl-section").scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  if (act === "ecg") { s.ecg = p.ecg_if_done; log(name, "ECG done"); }
  if (act === "trop") {
    const test = p.troponin_orders[s.ordersUsed];
    if (s.troponin.length) {
      const w = document.createElement("div");
      w.className = "waiting"; w.innerHTML = "<div>Repeat troponin: three hours later…</div>";
      document.body.append(w);
      await new Promise((r) => setTimeout(r, 1300));
      w.remove();
    }
    s.troponin.push(test); s.ordersUsed++;
    log(name, `${s.troponin.length > 1 ? "Repeat troponin" : "Troponin"}: ${test.value} ng/L`);
  }
  if (act === "senior") { s.outcome = { kind: "senior", time: new Date().toTimeString().slice(0, 5) }; log(name, "Senior review requested"); }
  if (act === "anyway" && s.anyway) { s.outcome = { kind: "anyway", reason: s.anyway }; log(name, `Discharged despite Second Look: ${s.anyway}`); }
  if (act === "record") {
    const a = s.answers;
    s.history = { pre_eclampsia: a[0], diabetes: a[2], previous_visits: a[3] ? [{ months_ago: 2 }] : [] };
    if (a[1]) s.history.months_since_pregnancy = p.months_since_pregnancy_if_asked ?? 6;
    log(name, "History taken at bedside");
  }
  const y = window.scrollY;
  renderAll();
  window.scrollTo({ top: y });
});

renderValidation();
renderAll();

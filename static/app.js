/* BillShield frontend.
   Talks to the FastAPI backend over /api/v1. Field names below must match
   the BillScenario schema in app/models.py — tests/test_contract.py checks
   that they do, so a rename on either side fails the build rather than
   silently dropping data. */

const API = '/api/v1';
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

let META = null;
let CASES = [];
let LAST = null;

const SEAL = {
  protected: 'Protected',
  not_protected: 'Outside federal law',
  waived: 'Likely waived',
  gfe_dispute: 'Disputable',
  needs_info: 'Incomplete',
};

const money = (n) =>
  n == null ? null : '$' + Number(n).toLocaleString('en-US',
    { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const esc = (s) => String(s).replace(/[&<>"']/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* ── boot ───────────────────────────────────────────── */

async function boot() {
  try {
    const [rules, cases] = await Promise.all([
      fetch(`${API}/rules`).then(r => r.json()),
      fetch(`${API}/scenarios`).then(r => r.json()),
    ]);
    META = rules;
    CASES = cases.scenarios;
    drawCases();
    drawIndex();
    fillMenus();
  } catch (e) {
    $('#case-files').innerHTML =
      `<div class="alert">The rule service didn't respond, so the form can't
       be filled in. ${esc(e.message)}</div>`;
  }
  wire();
}

function drawCases() {
  $('#case-files').innerHTML = CASES.map((c, i) => `
    <button type="button" class="file" data-i="${i}">
      <span class="ref">CASE ${String(i + 1).padStart(2, '0')}</span>
      <h3>${esc(c.title)}</h3>
      <p>${esc(c.story)}</p>
    </button>`).join('');

  $$('.file').forEach(el => el.addEventListener('click', () => {
    loadCase(CASES[+el.dataset.i].scenario);
    $('#check').scrollIntoView({ behavior: 'smooth' });
  }));
}

function drawIndex() {
  $('#rule-index').innerHTML = META.rules.map(r => `
    <div class="entry-row">
      <div><b>${esc(r.title)}</b><p>${esc(r.summary)}</p></div>
      <cite>${esc(r.citation)}</cite>
    </div>`).join('');
}

function fillMenus() {
  const all = { ...META.covered_facilities, ...META.non_covered_facilities };
  $('#facility_type').innerHTML = Object.entries(all)
    .map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join('');

  const opts = (obj) => Object.entries(obj)
    .map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join('');
  $('#specialty').innerHTML =
    `<optgroup label="Protection cannot be waived">${opts(META.ancillary_specialties)}</optgroup>` +
    `<optgroup label="Other specialties">${opts(META.waivable_specialties)}</optgroup>`;
  specialtyAside();
}

function specialtyAside() {
  const v = $('#specialty').value;
  const anc = v in (META?.ancillary_specialties || {});
  $('#specialty-aside').textContent = anc
    ? 'For this specialty a provider may not ask you to waive protection at all. You do not realistically get to choose who it is.'
    : 'For this specialty a provider may ask you to waive protection, if they follow the notice rules.';
}

/* ── form behaviour ─────────────────────────────────── */

function wire() {
  $$('input[name=coverage]').forEach(r => r.addEventListener('change', () => {
    switchPath(); resetSteps();
  }));
  $$('input[name=care_type]').forEach(r => r.addEventListener('change', () => {
    switchCare(); resetSteps();
  }));
  $('#signed_consent').addEventListener('change', e =>
    $('#consent-detail').classList.toggle('hidden', !e.target.checked));
  $('#specialty').addEventListener('change', specialtyAside);
  $('#form').addEventListener('submit', submit);
  $('#next').addEventListener('click', () => go(+1));
  $('#back').addEventListener('click', () => go(-1));
  $('#restart').addEventListener('click', restart);
  switchPath(); switchCare(); resetSteps();
}

function switchPath() {
  const self = $('input[name=coverage]:checked').value === 'uninsured_self_pay';
  $('#insured-path').classList.toggle('hidden', self);
  $('#selfpay-path').classList.toggle('hidden', !self);
}

function switchCare() {
  const v = $('input[name=care_type]:checked')?.value;
  const scheduled = v === 'scheduled';
  $('#scheduled-parts').classList.toggle('hidden', !scheduled);
  $('#consent-part').classList.toggle('hidden',
    !(scheduled || v === 'post_stabilization'));
  $('#state-part').classList.toggle('hidden', v !== 'ground_ambulance');
}

/* ── step machine ───────────────────────────────────────
   Steps are the .part fieldsets that apply to the chosen path. The set is
   recomputed whenever coverage or care type changes, because those answers
   decide which questions exist at all. */

let STEPS = [];
let at = 0;

function applicableSteps() {
  return [...$$('#form .part')].filter(el => !el.closest('.hidden'));
}

function resetSteps() {
  const wasAt = at;
  STEPS = applicableSteps();
  at = Math.min(wasAt, STEPS.length - 1);
  paintStep();
}

function restart() {
  $('#form').reset();
  $('#consent-detail').classList.add('hidden');
  $('#result').classList.add('hidden');
  switchPath(); switchCare();
  at = 0;
  resetSteps();
  $('#check').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function paintStep() {
  STEPS.forEach((el, i) => el.classList.toggle('off', i !== at));

  const last = at === STEPS.length - 1;
  $('#next').classList.toggle('hidden', last);
  $('#submit').classList.toggle('hidden', !last);
  $('#back').classList.toggle('hidden', at === 0);
  $('#restart').classList.toggle('hidden', at === 0);

  $('#step-count').textContent = `Step ${at + 1} of ${STEPS.length}`;
  $('#pips').innerHTML = STEPS.map((_, i) =>
    `<span class="pip ${i < at ? 'done' : i === at ? 'now' : ''}"></span>`
  ).join('');

  const err = $('#form').querySelector('.field-error');
  if (err) err.remove();
}

/* Only block on answers the engine genuinely needs. Amounts stay optional. */
function stepComplete(el) {
  const groups = new Set(
    [...el.querySelectorAll('input[type=radio]')].map(r => r.name)
  );
  for (const name of groups) {
    const any = [...el.querySelectorAll(`input[name="${name}"]`)]
      .some(r => r.checked);
    if (!any) return 'Choose an option to continue.';
  }
  return null;
}

function go(dir) {
  if (dir > 0) {
    const problem = stepComplete(STEPS[at]);
    if (problem) {
      const old = STEPS[at].querySelector('.field-error');
      if (old) old.remove();
      const p = document.createElement('p');
      p.className = 'field-error';
      p.textContent = problem;
      STEPS[at].appendChild(p);
      return;
    }
  }
  at = Math.max(0, Math.min(STEPS.length - 1, at + dir));
  paintStep();
  $('#check').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function loadCase(s) {
  $('#form').reset();
  const radio = (n, v) => {
    const el = document.querySelector(`input[name="${n}"][value="${v}"]`);
    if (el) el.checked = true;
  };
  radio('coverage', s.coverage || 'insured');
  radio('care_type', s.care_type);
  switchPath(); switchCare();

  if (s.facility_type) $('#facility_type').value = s.facility_type;
  if (s.specialty) { $('#specialty').value = s.specialty; specialtyAside(); }
  if (s.facility_in_network != null) radio('facility_in_network', s.facility_in_network);
  if (s.provider_in_network != null) radio('provider_in_network', s.provider_in_network);
  if (s.gfe_provided != null) radio('gfe_provided', s.gfe_provided);

  if (s.signed_consent) {
    $('#signed_consent').checked = true;
    $('#consent-detail').classList.remove('hidden');
    const h = document.querySelector('input[name=consent_hours_before]');
    if (h) h.value = s.consent_hours_before ?? '';
    const d = document.querySelector('input[name=same_day_scheduled]');
    if (d) d.checked = !!s.same_day_scheduled;
  }

  ['gfe_amount', 'billed_amount', 'in_network_cost_share', 'state'].forEach(n => {
    if (s[n] == null) return;
    document.querySelectorAll(`[name="${n}"]`).forEach(el => {
      if (!el.closest('.hidden')) el.value = s[n];
    });
  });

  /* A loaded case is already complete, so jump to the end and let the
     person press Assess rather than clicking through prefilled steps. */
  STEPS = applicableSteps();
  at = STEPS.length - 1;
  paintStep();
}

/* ── build the request ──────────────────────────────── */

function collect() {
  // .off means 'step not reached yet' and is still part of the path;
  // only .hidden means 'not applicable, do not send'.
  const shown = (el) => el && !el.closest('.hidden');
  const val = (n) => {
    const el = [...document.querySelectorAll(`[name="${n}"]`)]
      .find(e => shown(e) && (e.type !== 'radio' || e.checked));
    return el ? el.value : '';
  };
  const num = (n) => { const v = val(n); return v === '' ? null : Number(v); };
  const bool = (n) => { const v = val(n); return v === '' ? null : v === 'true'; };
  const tick = (n) => {
    const el = document.querySelector(`input[name="${n}"]`);
    return !!(el && shown(el) && el.checked);
  };

  const coverage = $('input[name=coverage]:checked').value;
  const care = coverage === 'uninsured_self_pay'
    ? 'scheduled'
    : $('input[name=care_type]:checked').value;

  const s = { care_type: care, coverage };

  if (coverage === 'uninsured_self_pay') {
    s.gfe_provided = bool('gfe_provided');
    s.gfe_amount = num('gfe_amount');
    s.billed_amount = num('billed_amount');
    return s;
  }

  if (care === 'scheduled') {
    s.facility_type = val('facility_type') || null;
    s.facility_in_network = bool('facility_in_network');
    s.provider_in_network = bool('provider_in_network');
    s.specialty = val('specialty') || null;
  }
  s.signed_consent = tick('signed_consent');
  if (s.signed_consent) {
    s.consent_hours_before = num('consent_hours_before');
    s.same_day_scheduled = tick('same_day_scheduled');
  }
  s.billed_amount = num('billed_amount');
  s.in_network_cost_share = num('in_network_cost_share');
  const st = val('state');
  if (st) s.state = st.toUpperCase();
  return s;
}

/* Turn a FastAPI 422 body into something a person can act on. */
function readError(body, status) {
  if (body && Array.isArray(body.detail)) {
    return body.detail.map(d => {
      const field = (d.loc || []).filter(x => x !== 'body').join(' ');
      return field ? `${field}: ${d.msg}` : d.msg;
    }).join('. ');
  }
  if (body && typeof body.detail === 'string') return body.detail;
  return `The server returned ${status}.`;
}

async function submit(e) {
  e.preventDefault();
  const btn = $('#submit');
  btn.disabled = true;
  btn.innerHTML = '<span class="working"></span>Assessing';

  const scenario = collect();
  try {
    const res = await fetch(`${API}/assess`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(scenario),
    });
    const body = await res.json().catch(() => null);
    if (!res.ok) throw new Error(readError(body, res.status));
    LAST = { scenario, assessment: body };
    draw(body);
  } catch (err) {
    $('#result').classList.remove('hidden');
    $('#result-body').innerHTML =
      `<div class="alert">Couldn't assess this bill. ${esc(err.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Assess this bill';
  }
}

/* ── render the determination ───────────────────────── */

function draw(a) {
  $('#result').classList.remove('hidden');

  const figure = a.estimated_balance_bill
    ? `<div class="figure"><b>${money(a.estimated_balance_bill)}</b>
       <span>${a.outcome === 'protected'
         ? 'billed above what you lawfully owe'
         : 'the amount in question'}</span></div>` : '';

  const needed = a.missing_facts?.length
    ? part('Still needed', `<ol class="actions">${
        a.missing_facts.map(m => `<li>${esc(m)}</li>`).join('')}</ol>`) : '';

  const cited = a.fired_rules?.length
    ? part('Rules that applied', a.fired_rules.map(r => `
        <div class="cited"><b>${esc(r.title)}</b><cite>${esc(r.citation)}</cite>
        <p>${esc(r.summary)}</p></div>`).join('')) : '';

  const owed = a.cost_sharing_note
    ? part('What you actually owe', `<p class="said">${esc(a.cost_sharing_note)}</p>`) : '';

  const swaps = a.counterfactuals?.length
    ? part('What would change this', a.counterfactuals.map(c => `
        <div class="swap"><i>${esc(c.change)}</i><em>then</em>
        <b>${esc(c.would_become)}</b></div>`).join('')) : '';

  const steps = a.next_steps?.length
    ? part('What to do next', `<ol class="actions">${
        a.next_steps.map(s => `<li>${esc(s)}</li>`).join('')}</ol>${
        a.deadline_days
          ? `<p class="clock">You have ${a.deadline_days} days from the date on your bill.</p>`
          : ''}`) : '';

  const state = a.state_note
    ? part('Your state', `<p class="said">${esc(a.state_note)}</p>`) : '';

  const letter = a.outcome !== 'needs_info' ? part('Send a dispute letter', `
      <p class="said">Written to match this determination and citing the same
         rules. Read it before you send it.</p>
      <div class="letter-fields">
        <label class="entry"><span>Your full name</span>
          <input type="text" id="l_name" placeholder="Required"></label>
        <label class="entry"><span>Provider or hospital</span>
          <input type="text" id="l_prov" placeholder="Required"></label>
        <label class="entry"><span>Account number</span>
          <input type="text" id="l_acct" placeholder="Optional"></label>
        <label class="entry"><span>Date of service</span>
          <input type="text" id="l_date" placeholder="Optional"></label>
      </div>
      <button type="button" class="act" id="l_go">Download the letter</button>
      <div id="l_err"></div>`) : '';

  $('#result-body').innerHTML = `
    <h2>Determination</h2>
    <div class="notice">
      <div class="notice-top ${a.outcome}">
        <span class="seal">${SEAL[a.outcome] || a.outcome}</span>
        <h3>${esc(a.headline)}</h3>
        <p>${esc(a.explanation)}</p>
        ${figure}
      </div>
      ${needed}${cited}${owed}${swaps}${steps}${state}${letter}
    </div>`;

  if ($('#l_go')) $('#l_go').addEventListener('click', download);
  $('#result').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

const part = (title, inner) =>
  `<div class="notice-part"><h4>${title}</h4>${inner}</div>`;

async function download() {
  const name = $('#l_name').value.trim();
  const prov = $('#l_prov').value.trim();
  const err = $('#l_err');
  err.innerHTML = '';

  if (!name || !prov) {
    err.innerHTML = '<div class="alert">Enter your name and the provider name to build the letter.</div>';
    return;
  }

  const btn = $('#l_go');
  btn.disabled = true;
  btn.innerHTML = '<span class="working"></span>Building';

  try {
    const res = await fetch(`${API}/letter`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scenario: LAST.scenario,
        patient_name: name,
        provider_name: prov,
        account_number: $('#l_acct').value.trim() || null,
        service_date: $('#l_date').value.trim() || null,
      }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new Error(readError(body, res.status));
    }
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement('a');
    a.href = url;
    a.download = `${name.replace(/\s+/g, '_')}_dispute.pdf`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    err.innerHTML = `<div class="alert">${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Download the letter';
  }
}

boot();

import {request} from './client.js';
import {snapshot, history} from './view.js';
import {visualize} from './plots.js';

const form = document.querySelector('#source');
const file = document.querySelector('#file');
const profile = document.querySelector('#profile');
const status = document.querySelector('#notice');
const detail = document.querySelector('#review');
const evidence = document.querySelector('#evidence');
const casePanel = document.querySelector('#case-panel');
const supplementPanel = document.querySelector('#supplement-panel');
const caseNote = document.querySelector('#case-note');
const supplementRow = document.querySelector('#supplement-row');
const stages = [...document.querySelectorAll('[data-stage]')];
let stage = 'balance';
let report, selected, batch, running = false;

function source() {
  const data = new FormData();
  if (file.files.length) data.append('file',file.files[0]);
  else data.append('sample',profile.value);
  return data;
}

function announce(text, failure = false) {
  status.textContent = text;
  status.dataset.failure = String(failure);
}

function draw() {
  if (!report) return;
  snapshot(report, selected, stage, {caseReviews: batch?.case_reviews || {}});
  visualize(report, selected);
  for (const button of stages) button.setAttribute('aria-pressed',String(button.dataset.stage===stage));
  document.querySelector('#panel-title').textContent = stages.find(button => button.dataset.stage===stage)?.textContent || '运行对账';
  detail.hidden = !batch;
  if (batch) {
    document.querySelector('#run-status').textContent = `${batch.id.slice(0,10)} · ${batch.status} · r${batch.revision}`;
    evidence.href = `/api/runs/${batch.id}/evidence`;
    drawCasePanel();
    drawSupplementPanel();
  }
}

function drawCasePanel() {
  const picked = report.cases?.find(row => row.case === selected);
  casePanel.hidden = !picked;
  if (!picked) return;
  const verdict = report.case_signability?.[picked.case];
  const review = batch.case_reviews?.[picked.case];
  const state = document.querySelector('#case-state');
  document.querySelector('#case-title').textContent = `分组 ${picked.case} 复核`;
  const parts = [];
  if (verdict) parts.push(verdict.signable ? '当前可签发' : `暂缓：${verdict.blockers.map(b => b.reason).join('、') || verdict.effective_status}`);
  if (review) {
    parts.push(`复核状态 ${review.status}（r${review.revision}）`);
    caseNote.value = review.note;
  }
  state.textContent = parts.join(' · ');
  const finalized = review?.status === 'APPROVED';
  const buttons = casePanel.querySelectorAll('button');
  buttons.forEach(button => { button.disabled = finalized; });
  caseNote.disabled = finalized;
  casePanel.querySelector('[value="APPROVED"]').disabled = finalized || !(verdict?.signable);
}

function drawSupplementPanel() {
  const picked = report.cases?.find(row => row.case === selected);
  const disputeId = picked?.dispute_ids?.[0];
  supplementPanel.hidden = !disputeId;
  if (!disputeId) return;
  const supplement = report.supplements?.[disputeId];
  const state = document.querySelector('#dispute-state');
  if (supplement) {
    state.textContent = `争议 ${disputeId} 已采信补证 → ${supplement.target_case}，复算：${JSON.stringify(supplement.outcomes)}`;
    supplementRow.disabled = true;
    supplementPanel.querySelector('button').disabled = true;
  } else {
    state.textContent = `争议 ${disputeId} 待裁决，涉及 ${report.disputes.find(d => d.dispute_id === disputeId)?.cases.join('、')}`;
    supplementRow.disabled = false;
    supplementPanel.querySelector('button').disabled = false;
  }
}

function show(payload, committed = false) {
  batch = committed ? payload : null;
  report = committed ? payload.report : payload;
  selected = report.cases?.[0]?.case;
  draw();
}

async function refresh() {
  const data = await request('/api/runs');
  history(data.items, batch?.id);
}

async function perform(action) {
  if (running) return;
  running = true;
  document.body.setAttribute('aria-busy','true');
  announce('处理中…');
  try { await action(); }
  catch (error) { announce(error.message,true); }
  finally { running = false; document.body.removeAttribute('aria-busy'); }
}

function preview(next) {
  return perform(async () => {
    const payload = await request(`/api/stages/${next}`,{method:'POST',body:source()});
    stage = next;
    show(payload);
    announce('阶段预览已更新');
    await refresh();
  });
}

stages.forEach(button => button.addEventListener('click',()=>preview(button.dataset.stage)));
form.addEventListener('submit', event => {
  event.preventDefault();
  perform(async () => {
    const result = await request('/api/runs',{method:'POST',body:source()});
    stage = 'balance'; show(result,true);
    announce('批次已保存'); await refresh();
  });
});
const filename = document.querySelector('#file-name');
profile.addEventListener('change',()=>{file.value=''; filename.textContent=''; preview(stage);});
file.addEventListener('change',()=>{filename.textContent=file.files[0]?.name || ''; preview(stage);});
document.querySelector('#rows').addEventListener('click',event=>{
  const button = event.target.closest('[data-case]');
  if (button) { selected = button.dataset.case; draw(); document.querySelector(`[data-case="${CSS.escape(selected)}"]`).focus(); }
});
document.querySelector('#history').addEventListener('click',event=>{
  const button = event.target.closest('[data-run]');
  if (button) perform(async()=>{
    const result = await request(`/api/runs/${button.dataset.run}`);
    stage='balance'; show(result,true); announce('已载入历史批次'); await refresh();
  });
});
casePanel.addEventListener('submit', event => {
  event.preventDefault();
  perform(async()=>{
    const review = batch.case_reviews?.[selected];
    const payload = {revision: review?.revision ?? 0, status: event.submitter.value, note: caseNote.value};
    const result = await request(`/api/runs/${batch.id}/cases/${encodeURIComponent(selected)}`,
      {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    const refreshed = await request(`/api/runs/${batch.id}`);
    show(refreshed, true);
    announce(result.status === 'APPROVED' ? `分组 ${selected} 已签发` : `分组 ${selected} 已暂缓`);
    await refresh();
  });
});
function parseCsvLine(text) {
  const cells = [];
  let field = '', quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (quoted) {
      if (char === '"') {
        if (text[i + 1] === '"') { field += '"'; i += 1; }
        else quoted = false;
      } else field += char;
    } else if (char === '"') {
      quoted = true;
    } else if (char === ',') {
      cells.push(field); field = '';
    } else field += char;
  }
  cells.push(field);
  return cells;
}

supplementPanel.addEventListener('submit', event => {
  event.preventDefault();
  perform(async()=>{
    const picked = report.cases.find(row => row.case === selected);
    const disputeId = picked.dispute_ids[0];
    const row = parseCsvLine(supplementRow.value).map(cell => cell.trim());
    await request(`/api/runs/${batch.id}/supplements`,
      {method:'POST', headers:{'Content-Type':'application/json'},
       body:JSON.stringify({dispute_id: disputeId, row})});
    const refreshed = await request(`/api/runs/${batch.id}`);
    show(refreshed, true);
    announce(`争议 ${disputeId} 补证已采信并完成复算`);
    await refresh();
  });
});
preview(stage);

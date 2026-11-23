import fixtures from './generated/fixtures.json';
import { executeRun } from './pipeline.js';

const now = () => new Date().toISOString();
export const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } });
export class ApiError extends Error { constructor(status, message) { super(message); this.status = status; } }
const fail = (status, message) => { throw new ApiError(status, message); };
const decode = (value, fallback = {}) => value ? JSON.parse(value) : fallback;
const one = (env, sql, ...params) => env.DB.prepare(sql).bind(...params).first();
const all = async (env, sql, ...params) => (await env.DB.prepare(sql).bind(...params).all()).results;
const write = (env, sql, ...params) => env.DB.prepare(sql).bind(...params).run();
export const fromBase64 = value => Uint8Array.from(atob(value), c => c.charCodeAt(0));

let seedPromise;
async function initialize(env) {
  if (!env.DB || !env.BUCKET) fail(503, 'Hosted database or document storage is unavailable.');
  if (!seedPromise) seedPromise = (async () => {
    const existing = await one(env, "SELECT key FROM settings WHERE key='rule_version'");
    if (!existing) await env.DB.batch(Object.entries(fixtures.settings).map(([key, value]) => env.DB.prepare('INSERT OR IGNORE INTO settings VALUES (?,?)').bind(key, JSON.stringify(value))));
    const vendors = await one(env, 'SELECT count(*) AS total FROM vendors_existing');
    if (!vendors.total) await env.DB.batch(fixtures.vendors.map(v => env.DB.prepare('INSERT OR IGNORE INTO vendors_existing(id,legal_name,trade_name,country,tax_id,bank_account,iban,status,email_domain,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)').bind(v.id,v.legal_name,v.trade_name,v.country,v.tax_id,v.bank_account,v.iban,v.status,v.email_domain,v.created_at || now())));
  })().catch(error => { seedPromise = null; throw error; });
  await seedPromise;
}

export async function settings(env) {
  return Object.fromEntries((await all(env, 'SELECT * FROM settings')).map(r => [r.key, decode(r.value_json)]));
}

function scenarioList() {
  // Keep submitted fields aligned with the actual bytes of the generated evidence.
  return fixtures.manifest.scenarios;
}

async function requireRun(env, id) {
  const row = await one(env, 'SELECT * FROM runs WHERE id=?', id);
  if (!row) fail(404, 'Review run not found.');
  return row;
}

export function validateSettings(value, current) {
  if (!value || Array.isArray(value) || typeof value !== 'object') fail(422, 'Settings must be a JSON object.');
  for (const [key, item] of Object.entries(value)) {
    if (!(key in current)) fail(422, `Unknown setting: ${key}`);
    if (Array.isArray(current[key]) ? !Array.isArray(item) : typeof item !== typeof current[key]) fail(422, `Invalid type for ${key}`);
    if (typeof item === 'number' && (!Number.isFinite(item) || item < 0)) fail(422, `Invalid numeric setting: ${key}`);
  }
  const merged = { ...current, ...value };
  for (const key of ['name_match_threshold', 'extraction_confidence_min', 'sanctions_name_match_threshold']) {
    if (!(merged[key] >= 0 && merged[key] <= 1)) fail(422, `${key} must be between 0 and 1.`);
  }
  const band = merged.name_match_review_band;
  if (!(band.min >= 0 && band.min <= band.max && band.max <= 1 && band.max === merged.name_match_threshold)) fail(422, 'Review band must end at the name-match threshold.');
  if (!(Number.isInteger(merged.max_documents) && merged.max_documents >= 1 && merged.max_documents <= 4 && Number.isInteger(merged.min_documents) && merged.min_documents >= 0 && merged.min_documents <= merged.max_documents)) fail(422, 'Document limits must be integers between 0 and 4.');
  const risks = merged.risk_bands;
  if (!risks || !['low','medium','high'].every(k => Array.isArray(risks[k]) && risks[k].length === 2 && risks[k].every(Number.isInteger))) fail(422, 'Risk bands must be integer ranges.');
  if (!(risks.low[0] === 0 && risks.low[1] + 1 === risks.medium[0] && risks.medium[1] + 1 === risks.high[0] && risks.high[1] === 100 && Object.values(risks).every(b => b[0] <= b[1]))) fail(422, 'Risk bands must cover 0-100 without gaps.');
  for (const key of ['free_mail_domains','sanctions_list','high_risk_jurisdictions','required_form_fields','eu_countries']) {
    if (!Array.isArray(merged[key]) || !merged[key].every(v => typeof v === 'string' && v.trim())) fail(422, `${key} must contain nonempty strings.`);
  }
  if (!merged.required_docs || !Object.values(merged.required_docs).every(docs => Array.isArray(docs) && docs.every(item => typeof item === 'string' || (Array.isArray(item) && item.length && item.every(s => typeof s === 'string'))))) fail(422, 'Required-document policies must contain document types or alternative type lists.');
  if (!merged.risk_signal_weights || !Object.values(merged.risk_signal_weights).every(v => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 100)) fail(422, 'Risk weights must be between 0 and 100.');
  return merged;
}

async function saveSubmission(env, form, docs, parent = null) {
  if (!form || Array.isArray(form) || typeof form !== 'object') fail(422, 'form_json must be a JSON object.');
  if (parent && !await one(env, 'SELECT id FROM submissions WHERE id=?', parent)) fail(404, 'Parent submission not found.');
  const id = crypto.randomUUID();
  await write(env, 'INSERT INTO submissions(id,parent_submission_id,form_json,created_at) VALUES (?,?,?,?)', id, parent, JSON.stringify(form), now());
  for (const doc of docs) await write(env, 'INSERT INTO documents(submission_id,filename,path) VALUES (?,?,?)', id, doc.filename, doc.path);
  return id;
}

async function loadScenario(env, id) {
  const scenario = scenarioList().find(s => s.id === id);
  if (!scenario) fail(404, 'Scenario not found.');
  let parent = null;
  if (scenario.parent_submission_id) parent = await loadScenario(env, scenario.parent_submission_id);
  return saveSubmission(env, scenario.form, scenario.documents.map(filename => ({filename, path: `fixture:${filename}`})), parent);
}

async function uploadSubmission(request, env, parent) {
  const config = await settings(env);
  if (Number(request.headers.get('content-length') || 0) > config.max_upload_bytes * config.max_documents + 65536) fail(413, 'Submission is too large.');
  const body = await request.formData();
  let form;
  try { form = JSON.parse(body.get('form_json')); } catch { fail(422, 'form_json must be valid JSON.'); }
  const files = body.getAll('files').filter(file => file && typeof file.arrayBuffer === 'function' && file.name);
  if (files.length > config.max_documents) fail(422, `Upload at most ${config.max_documents} documents.`);
  const docs = [];
  const prefix = crypto.randomUUID();
  try {
    for (const file of files) {
      if (file.size > config.max_upload_bytes) fail(413, `Each document must be at most ${Math.floor(config.max_upload_bytes / 1048576)} MB.`);
      const bytes = new Uint8Array(await file.arrayBuffer());
      const signature = String.fromCharCode(...bytes.slice(0, 12));
      const isPDF = signature.startsWith('%PDF-');
      const isPNG = bytes[0] === 137 && signature.slice(1,4) === 'PNG';
      const isJPEG = bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255;
      const isWEBP = signature.startsWith('RIFF') && signature.slice(8,12) === 'WEBP';
      if (!(isPDF || isPNG || isJPEG || isWEBP)) fail(422, 'Only valid PDF, PNG, JPEG or WebP documents are accepted.');
      const filename = file.name.split(/[\\/]/).pop().replace(/[^a-zA-Z0-9._ -]/g, '_').slice(0,160) || 'document';
      const path = `uploads/${prefix}/${crypto.randomUUID()}`;
      await env.BUCKET.put(path, bytes, {httpMetadata: {contentType: isPDF ? 'application/pdf' : isPNG ? 'image/png' : isJPEG ? 'image/jpeg' : 'image/webp'}});
      docs.push({filename, path});
    }
    const submissionId = await saveSubmission(env, form, docs, parent || body.get('parent_submission_id') || null);
    return json({submission_id: submissionId}, 201);
  } catch (error) {
    // Remove only the new objects for an unsuccessful upload, never prior evidence.
    await Promise.all(docs.map(doc => env.BUCKET.delete(doc.path)));
    throw error;
  }
}

async function createRun(env, submissionId, parentRunId = null) {
  if (!await one(env, 'SELECT id FROM submissions WHERE id=?', submissionId)) fail(404, 'Submission not found.');
  if (!parentRunId) {
    const parent = await one(env, 'SELECT parent_submission_id FROM submissions WHERE id=?', submissionId);
    if (parent?.parent_submission_id) parentRunId = (await one(env, 'SELECT id FROM runs WHERE submission_id=? ORDER BY id DESC LIMIT 1', parent.parent_submission_id))?.id || null;
  }
  const result = await write(env, "INSERT INTO runs(submission_id,parent_run_id,status,started_at) VALUES (?,?,'queued',?)", submissionId, parentRunId, now());
  return result.meta.last_row_id;
}

async function runPipeline(env, id) {
  // Compare-and-set is the lease: concurrent/reconnecting streams cannot duplicate a run.
  const lease = await write(env, "UPDATE runs SET status='running',started_at=? WHERE id=? AND status='queued'", now(), id);
  if (!lease.meta.changes) return;
  try {
    const run = await requireRun(env, id);
    const submission = await one(env, 'SELECT * FROM submissions WHERE id=?', run.submission_id);
    const docs = await all(env, 'SELECT * FROM documents WHERE submission_id=? ORDER BY id', run.submission_id);
    for (const doc of docs) {
      if (doc.path.startsWith('fixture:')) {
        const source = fixtures.assets[doc.path.slice(8)];
        if (!source) throw new Error('Fixture document is missing.');
        doc.bytes = fromBase64(source.base64);
        doc.extracted_text = source.extracted_text;
        doc.content_type = 'application/pdf';
      } else {
        const object = await env.BUCKET.get(doc.path);
        if (!object) throw new Error('Uploaded document is missing.');
        doc.bytes = new Uint8Array(await object.arrayBuffer());
        doc.content_type = object.httpMetadata?.contentType || 'application/octet-stream';
      }
    }
    const configuration = await settings(env);
    const vendors = await all(env, 'SELECT * FROM vendors_existing');
    const persist = async stage => {
      const existing = await one(env,'SELECT id FROM stage_results WHERE run_id=? AND stage_no=?',id,stage.stage_no);
      if (existing) await write(env,'UPDATE stage_results SET status=?,output_json=?,duration_ms=? WHERE id=?',stage.status,JSON.stringify(stage.output_json || {}),stage.duration_ms || 0,existing.id);
      else await write(env, 'INSERT INTO stage_results(run_id,stage_no,stage_name,stage_type,status,input_json,output_json,started_at,duration_ms,rule_version) VALUES (?,?,?,?,?,?,?,?,?,?)', id, stage.stage_no, stage.stage_name, stage.stage_type, stage.status, JSON.stringify(stage.input_json || {}), JSON.stringify(stage.output_json || {}), stage.started_at || now(), stage.duration_ms || 0, stage.rule_version || configuration.rule_version);
      const extracted = stage.output_json?.data?.documents;
      if (stage.stage_no === 2 && Array.isArray(extracted)) for (const doc of extracted) {
        const documentId = doc.id || doc.document_id;
        if (documentId && doc.doc_type) await write(env, 'UPDATE documents SET doc_type_detected=? WHERE id=? AND submission_id=?', doc.doc_type, documentId, run.submission_id);
      }
    };
    const outcome = await executeRun(env, id, configuration, vendors, {...submission, form: decode(submission.form_json)}, docs, persist);
    const {stages: ignoredStages, messages: drafts, ...decision} = outcome;
    const statements = [env.DB.prepare("UPDATE runs SET status='completed',risk_score=?,decision_json=?,finished_at=? WHERE id=?").bind(outcome.risk_score,JSON.stringify(decision),now(),id)];
    for (const draft of drafts || []) statements.push(env.DB.prepare('INSERT INTO messages_outbox(run_id,audience,subject,body) VALUES (?,?,?,?)').bind(id,draft.audience,draft.subject,draft.body));
    await env.DB.batch(statements);
  } catch (error) {
    console.error('VendorGate run failed', id, error?.name || 'Error');
    await write(env, "UPDATE runs SET status='failed',decision_json=?,finished_at=? WHERE id=?", JSON.stringify({decision:'PENDING',reasons:[{stage_no:0,field:'pipeline',message:'Review interrupted. Inspect the audit trail and rerun; no approval was issued.',evidence:[]}],what_would_change:['Rerun after correcting the configuration or document issue.'],risk_breakdown:[],confidence:0}), now(),id);
  }
}

function elapsed(run) { return run.finished_at && run.started_at ? Math.max(0,Date.parse(run.finished_at)-Date.parse(run.started_at)) : null; }
function runSummary(run) {
  const form = decode(run.form_json);
  const decision = decode(run.decision_json);
  return {run_id:run.id, vendor_name:form.legal_name || 'Unnamed vendor', country:form.country || '', decision:decision.decision || null, risk_score:run.risk_score, status:run.status, duration_ms:elapsed(run), created_at:run.started_at, parent_run_id:run.parent_run_id};
}

async function detail(env, id) {
  const run = await requireRun(env,id);
  const submission = await one(env,'SELECT * FROM submissions WHERE id=?',run.submission_id);
  const decision = decode(run.decision_json);
  const stages = (await all(env,'SELECT * FROM stage_results WHERE run_id=? ORDER BY stage_no,id',id)).map(s => {
    const output = decode(s.output_json);
    return {...s, name:s.stage_name, type:s.stage_type, summary:output.summary || '', findings:output.findings || [], data:output.data || {}, input_json:decode(s.input_json), output_json:output};
  });
  let diff = null;
  if (run.parent_run_id) {
    const parent = await requireRun(env,run.parent_run_id);
    const oldReasons = decode(parent.decision_json).reasons || [];
    const reasons = decision.reasons || [];
    const key = r => `${r.stage_no}:${r.field}:${r.message}`;
    diff = {resolved:oldReasons.filter(r=>!reasons.some(n=>key(n)===key(r))), still_open:reasons.filter(r=>oldReasons.some(n=>key(n)===key(r))), new:reasons.filter(r=>!oldReasons.some(n=>key(n)===key(r)))};
  }
  return {run_id:run.id,submission_id:run.submission_id,parent_run_id:run.parent_run_id,status:run.status,decision:decision.decision || null,risk_score:run.risk_score,risk_breakdown:decision.risk_breakdown || [],reasons:decision.reasons || [],what_would_change:decision.what_would_change || [],confidence:decision.confidence ?? null,form:decode(submission.form_json),documents:(await all(env,'SELECT * FROM documents WHERE submission_id=?',run.submission_id)).map(d=>({...d,url:`/api/documents/${d.id}/file`})),stages,messages:await all(env,'SELECT * FROM messages_outbox WHERE run_id=? ORDER BY id',id),overrides:await all(env,'SELECT * FROM overrides WHERE run_id=? ORDER BY id',id),diff_from_parent:diff,started_at:run.started_at,finished_at:run.finished_at,elapsed_ms:elapsed(run),llm_provider:decision.llm_provider || null};
}

async function events(request,env,id) {
  await requireRun(env,id);
  const encoder = new TextEncoder();
  let cancelled = false;
  const previous = Number(request.headers.get('last-event-id') || 0);
  const stream = new ReadableStream({
    async start(controller) {
      let sequence = 0;
      const send = (type,data) => { sequence += 1; if (!cancelled && sequence > previous) controller.enqueue(encoder.encode(`id: ${sequence}\nevent: ${type}\ndata: ${JSON.stringify(data)}\n\n`)); };
      const job = runPipeline(env,id);
      try {
        send('run_started',{run_id:id,started_at:(await requireRun(env,id)).started_at});
        const delivered = new Set(), started = new Set();
        let ticks = 0;
        while (!cancelled) {
          const rows = await all(env,'SELECT * FROM stage_results WHERE run_id=? ORDER BY stage_no,id',id);
          for (const row of rows) if (!delivered.has(row.id)) {
            if (!started.has(row.id)) { send('stage_started',{stage_no:row.stage_no,name:row.stage_name,type:row.stage_type}); started.add(row.id); }
            if (row.status==='running' || row.status==='queued') continue;
            const output = decode(row.output_json);
            send('stage_completed',{stage_no:row.stage_no,name:row.stage_name,type:row.stage_type,status:row.status,summary:output.summary || '',duration_ms:row.duration_ms,findings:output.findings || [],data:output.data || {}});
            delivered.add(row.id);
          }
          const run = await requireRun(env,id);
          if (run.status === 'completed') { const result=decode(run.decision_json); send('run_completed',{run_id:id,decision:result.decision,risk_score:run.risk_score,elapsed_ms:elapsed(run)}); break; }
          if (run.status === 'failed') { send('run_error',{message:'Review interrupted; no approval issued. Open audit details and rerun.'}); break; }
          if (++ticks % 25 === 0) controller.enqueue(encoder.encode(': heartbeat\n\n'));
          await new Promise(resolve=>setTimeout(resolve,200));
        }
        await job;
      } catch { if (!cancelled) send('run_error',{message:'Review stream interrupted. Reopen the run to reconnect.'}); }
      finally { if (!cancelled) controller.close(); }
    },
    cancel() { cancelled = true; },
  });
  return new Response(stream,{headers:{'content-type':'text/event-stream','cache-control':'no-cache, no-transform','x-accel-buffering':'no'}});
}

async function dashboard(env) {
  const rows = await all(env,'SELECT r.*,s.form_json FROM runs r JOIN submissions s ON s.id=r.submission_id ORDER BY r.id DESC');
  const complete = rows.filter(r=>r.status==='completed');
  const summaries = complete.map(runSummary);
  const counts = ['APPROVED','PENDING','REJECTED'].map(decision=>({decision,count:summaries.filter(r=>r.decision===decision).length}));
  const overridden = new Set((await all(env,'SELECT DISTINCT run_id FROM overrides')).map(r=>r.run_id));
  const reasonCounts = new Map();
  for (const run of complete) for (const reason of decode(run.decision_json).reasons || []) reasonCounts.set(reason.message,(reasonCounts.get(reason.message)||0)+1);
  const total = complete.length;
  const percent = count=>total?Math.round(count/total*1000)/10:0;
  const config = await settings(env);
  return {total:rows.length,completed:total,auto_approved_pct:percent(summaries.filter(r=>r.decision==='APPROVED'&&!overridden.has(r.run_id)).length),pending_pct:percent(counts[1].count),rejected_pct:percent(counts[2].count),avg_review_ms:total?Math.round(complete.reduce((sum,r)=>sum+(elapsed(r)||0),0)/total):0,flags_caught:complete.reduce((sum,r)=>sum+(decode(r.decision_json).reasons||[]).length,0),manual_hours_saved:0,manual_hours_saved_note:'No measured manual-review baseline has been configured.',outcomes:counts,top_reasons:[...reasonCounts].map(([reason,count])=>({reason,count})).sort((a,b)=>b.count-a.count).slice(0,5)};
}

export async function api(request,env) {
  const url = new URL(request.url);
  const path = url.pathname;
  if (path === '/health') { await initialize(env); await one(env,'SELECT 1 AS ok'); return json({ok:true}); }
  await initialize(env);
  if (path === '/api/runtime') return json({llm_provider:env.LLM_PROVIDER || 'mock',demo_mode:(env.LLM_PROVIDER || 'mock')==='mock',delivery_mode:'manual_outbox'});
  if (path === '/api/scenarios' && request.method === 'GET') return json(scenarioList());
  if (path === '/api/assumptions') return json({markdown:fixtures.assumptions});
  if (path === '/api/settings') {
    const current = await settings(env);
    if (request.method === 'GET') return json(current);
    if (request.method === 'PUT') {
      const next = validateSettings(await request.json(),current);
      next.rule_version = `1.0.${Date.now()}`;
      await env.DB.batch(Object.entries(next).map(([key,value])=>env.DB.prepare('INSERT INTO settings(key,value_json) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json').bind(key,JSON.stringify(value))));
      return json(next);
    }
  }
  if (path === '/api/dashboard/stats') return json(await dashboard(env));
  let match;
  if ((match=path.match(/^\/api\/scenarios\/([^/]+)\/load$/)) && request.method==='POST') return json({submission_id:await loadScenario(env,decodeURIComponent(match[1]))},201);
  if (path==='/api/submissions' && request.method==='POST') return uploadSubmission(request,env,null);
  if ((match=path.match(/^\/api\/submissions\/([^/]+)\/resubmit$/)) && request.method==='POST') return uploadSubmission(request,env,decodeURIComponent(match[1]));
  if ((match=path.match(/^\/api\/submissions\/([^/]+)\/runs$/)) && request.method==='POST') return json({run_id:await createRun(env,decodeURIComponent(match[1]))},201);
  if ((match=path.match(/^\/api\/runs\/(\d+)\/events$/))) return events(request,env,Number(match[1]));
  if ((match=path.match(/^\/api\/runs\/(\d+)\/rerun$/)) && request.method==='POST') { const run=await requireRun(env,Number(match[1])); return json({run_id:await createRun(env,run.submission_id,run.id)},201); }
  if ((match=path.match(/^\/api\/runs\/(\d+)\/override$/)) && request.method==='POST') {
    const id=Number(match[1]),run=await requireRun(env,id),body=await request.json();
    if (run.status!=='completed') fail(409,'Only completed reviews can be overridden.');
    if (!['APPROVED','PENDING','REJECTED'].includes(body.new_status) || typeof body.reason!=='string' || body.reason.trim().length<3) fail(422,'Choose a decision and supply an override reason of at least three characters.');
    const original=decode(run.decision_json);
    if (original.decision===body.new_status) fail(422,'Choose a different decision.');
    await env.DB.batch([
      env.DB.prepare('INSERT INTO overrides(run_id,reason,old_status,new_status,created_at) VALUES (?,?,?,?,?)').bind(id,body.reason.trim(),original.decision,body.new_status,now()),
      env.DB.prepare('UPDATE runs SET decision_json=? WHERE id=?').bind(JSON.stringify({...original,original_decision:original.original_decision||original.decision,decision:body.new_status,manual_override:true}),id),
    ]);
    return json(await detail(env,id));
  }
  if ((match=path.match(/^\/api\/runs\/(\d+)\/send$/)) && request.method==='POST') {
    const id=Number(match[1]); await requireRun(env,id);
    const drafts=await all(env,'SELECT * FROM messages_outbox WHERE run_id=?',id);
    if (!drafts.length) fail(409,'No draft messages are available.');
    const timestamp=now(); await write(env,'UPDATE messages_outbox SET sent_at=COALESCE(sent_at,?) WHERE run_id=?',timestamp,id);
    return json({sent_at:timestamp,delivery_mode:'manual_outbox',notice:'Recorded as sent by the operator. This application does not send email.'});
  }
  if ((match=path.match(/^\/api\/messages\/(\d+)$/)) && request.method==='PUT') {
    const id=Number(match[1]),message=await one(env,'SELECT * FROM messages_outbox WHERE id=?',id),body=await request.json();
    if (!message) fail(404,'Message not found.');
    if (message.sent_at) fail(409,'A message recorded as sent cannot be edited.');
    if (typeof body.subject!=='string'||!body.subject.trim()||typeof body.body!=='string'||!body.body.trim()) fail(422,'Subject and body are required.');
    await write(env,'UPDATE messages_outbox SET subject=?,body=? WHERE id=?',body.subject.trim(),body.body.trim(),id);
    return json(await one(env,'SELECT * FROM messages_outbox WHERE id=?',id));
  }
  if ((match=path.match(/^\/api\/documents\/(\d+)\/file$/))) {
    const doc=await one(env,'SELECT * FROM documents WHERE id=?',Number(match[1]));
    if (!doc) fail(404,'Document not found.');
    let bytes,type;
    if (doc.path.startsWith('fixture:')) { const asset=fixtures.assets[doc.path.slice(8)]; if (!asset) fail(404,'Document asset not found.'); bytes=fromBase64(asset.base64);type='application/pdf'; }
    else { const object=await env.BUCKET.get(doc.path);if (!object) fail(404,'Document asset not found.');bytes=object.body;type=object.httpMetadata?.contentType||'application/octet-stream'; }
    return new Response(bytes,{headers:{'content-type':type,'content-disposition':`inline; filename="${doc.filename.replace(/["\r\n]/g,'_')}"`,'cache-control':'private, no-store','x-content-type-options':'nosniff'}});
  }
  if ((match=path.match(/^\/api\/runs\/(\d+)$/))) return json(await detail(env,Number(match[1])));
  if (path==='/api/runs') {
    const limit=Math.min(100,Math.max(1,Number(url.searchParams.get('limit'))||20));
    const offset=Math.max(0,Number(url.searchParams.get('offset'))||0);
    const q=(url.searchParams.get('q')||'').toLowerCase(),status=url.searchParams.get('status');
    const rows=(await all(env,'SELECT r.*,s.form_json FROM runs r JOIN submissions s ON s.id=r.submission_id ORDER BY r.id DESC')).map(runSummary).filter(r=>(!q||r.vendor_name.toLowerCase().includes(q)||String(r.run_id)===q)&&(!status||r.status===status||r.decision===status));
    return json({total:rows.length,items:rows.slice(offset,offset+limit)});
  }
  fail(404,'Endpoint not found.');
}

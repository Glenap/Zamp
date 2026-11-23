import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFile, readdir, mkdir, writeFile } from 'node:fs/promises';
import { build } from 'esbuild';

let api, database, env;
const fixtures = JSON.parse(await readFile('worker/generated/fixtures.json','utf8'));

// D1's API over an actual SQLite database: integration tests execute the deployed
// queries and real pipeline; only the remote storage transport is substituted.
class Statement {
  constructor(sql, params=[]) { this.sql=sql;this.params=params; }
  bind(...params) { return new Statement(this.sql,params); }
  async first() { return database.prepare(this.sql).get(...this.params) || null; }
  async all() { return {results:database.prepare(this.sql).all(...this.params)}; }
  async run() { const result=database.prepare(this.sql).run(...this.params);return {meta:{changes:Number(result.changes),last_row_id:Number(result.lastInsertRowid)}}; }
}

before(async()=>{
  await mkdir('.sites-runtime',{recursive:true});
  await build({entryPoints:['worker/api.js'],outfile:'.sites-runtime/api-test.mjs',bundle:true,format:'esm',platform:'node',target:'node22'});
  ({api}=await import('../.sites-runtime/api-test.mjs'));
  database=new DatabaseSync(':memory:');
  for (const filename of (await readdir('drizzle')).filter(n=>n.endsWith('.sql')).sort()) database.exec(await readFile(`drizzle/${filename}`,'utf8'));
  const objects=new Map();
  env={LLM_PROVIDER:'mock',DB:{prepare:sql=>new Statement(sql),batch:async statements=>{database.exec('BEGIN');try{const result=[];for(const s of statements)result.push(await s.run());database.exec('COMMIT');return result;}catch(error){database.exec('ROLLBACK');throw error;}}},BUCKET:{put:async(key,bytes,options)=>objects.set(key,{bytes:new Uint8Array(bytes),options}),get:async key=>{const object=objects.get(key);return object?{body:object.bytes,httpMetadata:object.options?.httpMetadata,arrayBuffer:async()=>object.bytes.buffer}:null;},delete:async key=>objects.delete(key)}};
});
after(()=>database?.close());

async function request(path,method='GET',body) {
  const response=await api(new Request(`http://localhost${path}`,{method,...(body instanceof FormData?{body}:body!==undefined?{body:JSON.stringify(body),headers:{'content-type':'application/json'}}:{})}),env);
  return response;
}
async function data(path,method='GET',body) { const response=await request(path,method,body);assert.ok(response.ok,`${path}: ${response.status}`);return response.json(); }
async function runScenario(id) {
  const {submission_id}=await data(`/api/scenarios/${id}/load`,'POST');
  const {run_id}=await data(`/api/submissions/${submission_id}/runs`,'POST');
  const response=await request(`/api/runs/${run_id}/events`);
  const events=await response.text();
  assert.match(events,/event: run_completed/);
  const run=await data(`/api/runs/${run_id}`);
  return {run,events};
}

test('hosted health, runtime and fixture manifest are honest',async()=>{
  assert.deepEqual(await data('/health'),{ok:true});
  assert.deepEqual(await data('/api/runtime'),{llm_provider:'mock',demo_mode:true,delivery_mode:'manual_outbox'});
  assert.equal((await data('/api/scenarios')).length,6);
  assert.equal(database.prepare('SELECT count(*) AS n FROM runs').get().n,0);
});

test('all six scenarios execute nine audited stages and stream real results',async()=>{
  for (const scenario of fixtures.manifest.scenarios) {
    const {run,events}=await runScenario(scenario.id);
    assert.equal(run.decision,scenario.expected_decision,`${scenario.id}: ${JSON.stringify(run.reasons)}`);
    assert.equal(run.stages.length,9);
    assert.equal((events.match(/event: stage_completed/g)||[]).length,9);
    for (const stage of run.stages) {
      assert.ok(['AI','RULE'].includes(stage.type));assert.ok(stage.started_at);assert.ok(stage.rule_version);
      assert.ok(stage.input_json);assert.ok(stage.output_json);assert.ok(stage.duration_ms>=0);
    }
    assert.equal(run.status,'completed');
    const evidence=await request(run.documents[0].url);
    assert.equal(evidence.headers.get('content-type'),'application/pdf');
    assert.ok((await evidence.arrayBuffer()).byteLength>1000);
  }
});

test('outbox edits, recorded delivery and overrides retain audit',async()=>{
  const {run}=await runScenario('S2');
  assert.ok(run.messages.length);
  const draft=run.messages[0];
  const updated=await data(`/api/messages/${draft.id}`,'PUT',{subject:'Reviewed subject',body:'Please provide evidence for the bank-holder alias.'});
  assert.equal(updated.subject,'Reviewed subject');
  const sent=await data(`/api/runs/${run.run_id}/send`,'POST');
  assert.equal(sent.delivery_mode,'manual_outbox');assert.match(sent.notice,/does not send email/);
  await assert.rejects(()=>request(`/api/messages/${draft.id}`,'PUT',{subject:'changed',body:'changed'}),/cannot be edited/);
  await assert.rejects(()=>request(`/api/runs/${run.run_id}/override`,'POST',{new_status:'APPROVED',reason:''}),/reason/);
  const override=await data(`/api/runs/${run.run_id}/override`,'POST',{new_status:'APPROVED',reason:'Alias independently verified by operator for this synthetic demo.'});
  assert.equal(override.decision,'APPROVED');assert.equal(override.overrides.length,1);assert.equal(override.overrides[0].old_status,'PENDING');
  assert.equal(override.stages[6].data.decision,'PENDING');
});

test('settings validation and history filters use actual stored values',async()=>{
  const current=await data('/api/settings');
  await assert.rejects(()=>request('/api/settings','PUT',{name_match_threshold:2}),/between 0 and 1/);
  const next=await data('/api/settings','PUT',{...current,free_mail_domains:[...current.free_mail_domains,'example.invalid']});
  assert.ok(next.free_mail_domains.includes('example.invalid'));
  const history=await data('/api/runs?q=Brightline&limit=1');assert.ok(history.total>=1);assert.equal(history.items.length,1);
  const stats=await data('/api/dashboard/stats');assert.ok(stats.total>=6);assert.ok(stats.flags_caught>0);
});

test('uploaded document bytes persist and resubmissions link to parents',async()=>{
  const body=new FormData();body.set('form_json',JSON.stringify(fixtures.manifest.scenarios[0].form));
  body.append('files',new Blob([Buffer.from(fixtures.assets['s1_w9.pdf'].base64,'base64')],{type:'application/pdf'}),'../../evidence.pdf');
  const uploaded=await data('/api/submissions','POST',body);
  const {run_id}=await data(`/api/submissions/${uploaded.submission_id}/runs`,'POST');
  await (await request(`/api/runs/${run_id}/events`)).text();
  const run=await data(`/api/runs/${run_id}`);
  assert.equal(run.documents[0].filename,'evidence.pdf');
  assert.equal(run.decision,'PENDING'); // Explicit mock cannot read custom image/PDF uploads.
  const child=new FormData();child.set('form_json',JSON.stringify(fixtures.manifest.scenarios[0].form));
  const resubmitted=await data(`/api/submissions/${uploaded.submission_id}/resubmit`,'POST',child);
  assert.equal(database.prepare('SELECT parent_submission_id FROM submissions WHERE id=?').get(resubmitted.submission_id).parent_submission_id,uploaded.submission_id);
  const invalid=new FormData();invalid.set('form_json','{}');invalid.append('files',new Blob(['<html>evil</html>']),'bad.pdf');
  await assert.rejects(()=>request('/api/submissions','POST',invalid),/Only valid/);
});

test('real-provider configuration failure never silently approves or uses mock',async()=>{
  env.LLM_PROVIDER='openai';
  const {run}=await runScenario('S1');
  assert.equal(run.decision,'PENDING');
  assert.ok(run.stages.some(stage=>stage.status==='needs_manual_review'));
  env.LLM_PROVIDER='mock';
});

import { FormEvent, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Form, post, request, Run, Scenario } from '../api/client';
import { Alert, Badge, Icon, Loading, PageTitle, useData } from '../components/common';

const blank: Form = { legal_name: '', trade_name: '', country: 'US', contact_name: '', contact_email: '', tax_id: '', bank_holder_name: '', bank_account: '', aba: '', iban: '', ifsc: '', bic: '', incorporated_on: '', annual_spend: 0, address: '' };

export function NewReview() {
  const scenarios = useData<Scenario[]>('/api/scenarios');
  const [form, setForm] = useState<Form>({ ...blank }); const [files, setFiles] = useState<File[]>([]); const [selected, setSelected] = useState<Scenario | null>(null);
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const [parent, setParent] = useState<Run | null>(null); const [parentLoading, setParentLoading] = useState(false);
  const [params] = useSearchParams(); const navigate = useNavigate();
  const resubmit = params.get('resubmit');
  useEffect(() => { if (!resubmit) return; setParentLoading(true); request<Run>(`/api/runs/${encodeURIComponent(resubmit)}`).then(run => { setParent(run); setForm({ ...blank, ...run.form }); }).catch(e => setError(e.message)).finally(() => setParentLoading(false)); }, [resubmit]);
  const update = (key: string, value: string) => setForm(old => ({ ...old, [key]: key === 'annual_spend' ? Number(value) : value }));
  function selectScenario(scenario: Scenario) { setSelected(scenario); setForm({ ...blank, ...scenario.form }); setFiles([]); setError(''); }
  function chooseFiles(list: FileList | null) {
    if (!list) return;
    const accepted = Array.from(list);
    if (accepted.length > 4) { setError('Choose up to four documents.'); return; }
    if (accepted.some(file => !['application/pdf', 'image/png', 'image/jpeg', 'image/webp'].includes(file.type))) { setError('Use PDF, PNG, JPEG, or WebP documents.'); return; }
    if (accepted.some(file => file.size > 10 * 1024 * 1024)) { setError('Each document must be no larger than 10 MB.'); return; }
    setError(''); setFiles(accepted); setSelected(null);
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      let submission: { submission_id: string };
      if (selected) submission = await post(`/api/scenarios/${encodeURIComponent(selected.id)}/load`);
      else {
        const multipart = new FormData();
        const data = { ...form, email_domain: String(form.contact_email || '').split('@')[1] || '', tax_id_type: form.country === 'US' ? 'EIN' : form.country === 'IN' ? 'GSTIN' : 'VAT' };
        multipart.append('form_json', JSON.stringify(data)); files.forEach(file => multipart.append('files', file));
        if (parent) multipart.append('parent_submission_id', parent.submission_id);
        submission = await post(parent ? `/api/submissions/${encodeURIComponent(parent.submission_id)}/resubmit` : '/api/submissions', multipart);
      }
      const run = await post<{ run_id: number }>(`/api/submissions/${encodeURIComponent(submission.submission_id)}/runs`);
      navigate(`/reviews/${run.run_id}`);
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  }
  const field = (label: string, key: string, options: { required?: boolean; type?: string; placeholder?: string } = {}) => <label className="field" key={key}><span>{label}{options.required && <span className="required"> *</span>}</span><input readOnly={!!selected} type={options.type || 'text'} required={options.required} value={form[key] ?? ''} onChange={e => update(key, e.target.value)} placeholder={options.placeholder} /></label>;
  return <><PageTitle eyebrow={parent ? 'CORRECTED SUBMISSION' : 'NEW VENDOR REVIEW'} title={parent ? 'A fresh review, with context.' : 'Start with the evidence.'} description={parent ? `Linked to review #${parent.run_id}. Upload the corrected documents to compare findings.` : 'Add vendor details and supporting documents, or explore a synthetic sample scenario.'} />
    {parentLoading ? <Loading /> : <div className="new-review-layout"><form onSubmit={submit} className="review-form">
      {error && <Alert>{error}</Alert>}{parent && <div className="info-note"><Icon name="info" size={18} />Resubmissions require all supporting documents, including unchanged evidence.</div>}
      {selected && <div className="selected-scenario"><div><span className="eyebrow">SYNTHETIC SCENARIO {selected.id}</span><strong>{selected.title}</strong><p>These details and sample documents will be loaded together.</p></div><button type="button" className="button secondary small-button" onClick={() => { setSelected(null); setFiles([]); }}>Use custom details</button></div>}
      <section className="card form-card"><div className="form-section-title"><span className="step-number">01</span><div><h2>Business information</h2><p>The legal entity and its primary contact.</p></div></div><div className="form-grid">{field('Legal business name', 'legal_name', { required: true, placeholder: 'e.g. Brightline Logistics LLC' })}{field('Trade name', 'trade_name', { placeholder: 'If different from the legal name' })}<label className="field"><span>Country <span className="required">*</span></span><select disabled={!!selected} value={form.country || 'US'} onChange={e => update('country', e.target.value)}><option value="US">United States</option><option value="IN">India</option><option value="DE">Germany</option><option value="GB">United Kingdom</option><option value="FR">France</option><option value="NL">Netherlands</option><option value="OTHER">Other</option></select></label>{field('Tax identifier', 'tax_id', { required: true, placeholder: 'EIN, GSTIN, or VAT number' })}{field('Contact name', 'contact_name')}{field('Business email', 'contact_email', { required: true, type: 'email', placeholder: 'name@company.example' })}{field('Incorporation date', 'incorporated_on', { type: 'date', required: true })}{field('Annual spend (USD equivalent)', 'annual_spend', { type: 'number' })}<div className="full-width">{field('Registered business address', 'address')}</div></div></section>
      <section className="card form-card"><div className="form-section-title"><span className="step-number">02</span><div><h2>Bank details</h2><p>These fields will be checked against the supplied evidence.</p></div></div><div className="form-grid">{field('Account holder name', 'bank_holder_name', { required: true })}{field('Account number', 'bank_account', { required: true })}{form.country === 'US' && field('ABA routing number', 'aba', { placeholder: '9 digits', required: true })}{form.country === 'IN' && field('IFSC', 'ifsc', { placeholder: 'e.g. HDFC0001234', required: true })}{!['US', 'IN'].includes(String(form.country)) && <>{field('IBAN', 'iban', { placeholder: 'Country code and account details' })}{field('BIC / SWIFT', 'bic')}</>}</div></section>
      <section className="card form-card"><div className="form-section-title"><span className="step-number">03</span><div><h2>Supporting documents</h2><p>Tax evidence, bank evidence, and incorporation documents.</p></div></div>{selected ? <div className="document-list">{selected.documents.map(name => <div className="document-row" key={name}><span className="document-icon"><Icon name="file" /></span><div><strong>{name}</strong><small>Synthetic sample document</small></div><span className="subtle-chip">PDF</span></div>)}</div> : <><label className="upload-zone"><Icon name="upload" size={28} /><strong>Choose supporting documents</strong><span>PDF, PNG, JPEG, or WebP · Up to 4 files · 10 MB each</span><input type="file" accept="application/pdf,image/png,image/jpeg,image/webp" multiple onChange={e => chooseFiles(e.target.files)} /></label>{files.length > 0 && <div className="document-list">{files.map(file => <div className="document-row" key={file.name}><Icon name="file" /><div><strong>{file.name}</strong><small>{(file.size / 1024).toFixed(0)} KB</small></div></div>)}</div>}</>}</section>
      <div className="submit-panel"><div><strong>Ready for a complete review?</strong><p>All nine stages and their reasoning will appear in the live timeline.</p></div><button className="button primary" type="submit" disabled={busy || (resubmit != null && !parent)}>{busy ? <><span className="spinner white" />Starting…</> : <><Icon name="bolt" size={18} />Run vendor review</>}</button></div>
    </form><aside className="review-aside">{!parent && <section className="card scenario-panel"><div className="eyebrow">EXPLORE THE WORKFLOW</div><h2>Try a sample scenario</h2><p>Fictional vendors and generated documents. Expected outcomes are shown for comparison.</p>{scenarios.error && <Alert>{scenarios.error}</Alert>}{scenarios.loading ? <Loading /> : scenarios.data?.map((scenario, index) => <button type="button" className={`scenario-button ${selected?.id === scenario.id ? 'selected' : ''}`} key={scenario.id} onClick={() => selectScenario(scenario)}><span className="scenario-number">{String(index + 1).padStart(2, '0')}</span><span><strong>{scenario.title || scenario.form.legal_name}</strong><small>{scenario.description}</small><Badge value={scenario.expected_decision} /></span></button>)}</section>}<section className="review-explainer"><Icon name="shield" size={24} /><h3>What happens next?</h3><p>Documents are read, required evidence is checked, and plain-code rules validate identifiers and consistency. Every finding stays attached to the review.</p><span>Checks indicate consistency, not document authenticity or payment eligibility.</span></section></aside></div>}
  </>;
}

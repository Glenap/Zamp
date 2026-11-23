import { useCallback, useEffect, useState } from 'react';
import { request } from '../api/client';

export function useData<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(() => {
    setLoading(true); setError('');
    return request<T>(path).then(setData).catch(e => setError(e.message)).finally(() => setLoading(false));
  }, [path]);
  useEffect(() => { let active = true; setLoading(true); setError(''); request<T>(path).then(value => { if (active) setData(value); }).catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [path]);
  return { data, error, loading, refresh, setData };
}

export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, React.ReactNode> = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
    plus: <><path d="M12 5v14M5 12h14" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    settings: <><path d="m9 3-1 3-3 1 1 3-2 2 2 2-1 3 3 1 1 3h6l1-3 3-1-1-3 2-2-2-2 1-3-3-1-1-3Z" /><circle cx="12" cy="12" r="3" /></>,
    file: <><path d="M14 3H5v18h14V8ZM14 3v5h5M8 12h8M8 16h6" /></>,
    shield: <><path d="m12 3 8 3v6c0 4-5 8-8 9-3-1-8-5-8-9V6Z" /><path d="m8 12 3 3 5-6" /></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    upload: <><path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6" /></>,
    arrow: <><path d="M5 12h14m-5-5 5 5-5 5" /></>,
    info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7h.01" /></>,
    bolt: <path d="m13 2-9 12h7l-1 8 10-13h-8Z" />,
    menu: <path d="M4 6h16M4 12h16M4 18h16" />,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.file}</svg>;
}

export function Badge({ value }: { value?: string | null }) {
  const key = (value || 'queued').toLowerCase();
  const tone = ['approved', 'passed', 'completed'].includes(key) ? 'green' : ['rejected', 'failed'].includes(key) ? 'red' : ['pending', 'warning', 'needs_manual_review'].includes(key) ? 'amber' : ['running'].includes(key) ? 'blue' : 'gray';
  return <span className={`badge ${tone}`}><span className="badge-dot" />{(value || 'Queued').replaceAll('_', ' ')}</span>;
}
export function Alert({ children }: { children: React.ReactNode }) { return <div className="alert" role="alert"><Icon name="info" size={18} /><span>{children}</span></div>; }
export function Loading() { return <div className="loading" role="status"><span className="spinner" />Loading workspace…</div>; }
export function Empty({ title, children }: { title: string; children?: React.ReactNode }) { return <div className="empty"><div className="empty-icon"><Icon name="file" size={28} /></div><h3>{title}</h3><p>{children}</p></div>; }
export function PageTitle({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: React.ReactNode }) { return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action}</div>; }
export const dateLabel = (value?: string | null) => value ? new Date(value.endsWith('Z') || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
export const textValue = (value: any): string => typeof value === 'string' ? value : value?.message || value?.detail || JSON.stringify(value);

import { useState } from 'react';
import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom';
import { Icon, useData } from './components/common';
import { Dashboard, History, Settings, Assumptions } from './pages/Workspace';
import { NewReview } from './pages/NewReview';
import { Review } from './pages/Review';

export function App() {
  const [menu, setMenu] = useState(false);
  const runtime = useData<{ llm_provider: string; demo_mode: boolean; delivery_mode: string }>('/api/runtime');
  const location = useLocation();
  const nav = [['/', 'grid', 'Overview'], ['/reviews/new', 'plus', 'New review'], ['/history', 'clock', 'Review history'], ['/settings', 'settings', 'Settings'], ['/assumptions', 'file', 'Assumptions']];
  return <div className="app-shell">
    <aside className={`sidebar ${menu ? 'open' : ''}`}>
      <Link to="/" className="brand" onClick={() => setMenu(false)}><span className="brand-mark"><Icon name="shield" size={25} /></span><span>VendorGate<span className="brand-sub">PROCUREMENT OPERATIONS</span></span></Link>
      <div className="workspace-label">WORKSPACE</div>
      <nav aria-label="Main navigation">{nav.map(([path, icon, label]) => <NavLink key={path} to={path} end={path === '/'} onClick={() => setMenu(false)} className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}><Icon name={icon} /><span>{label}</span>{path === '/reviews/new' && <span className="nav-plus">+</span>}</NavLink>)}</nav>
      <div className="sidebar-bottom"><div className="secure-note"><Icon name="shield" size={17} /><span>Every decision, traceable.</span></div><div className="profile"><span className="avatar">PO</span><div><strong>Procurement team</strong><small>Vendor onboarding workspace</small></div></div></div>
    </aside>
    {menu && <button className="menu-scrim" aria-label="Close navigation" onClick={() => setMenu(false)} />}
    <div className="main-shell"><header className="topbar"><div className="breadcrumb"><button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setMenu(!menu)}><Icon name="menu" /></button><span>Workspace</span><span className="crumb-divider">/</span><strong>{location.pathname.startsWith('/reviews/new') ? 'New review' : location.pathname.startsWith('/reviews/') ? 'Review details' : nav.find(([path]) => path === location.pathname)?.[2] || 'Workspace'}</strong></div><div className="topbar-right"><span className={`connection ${runtime.error ? 'offline' : ''}`} />{runtime.error ? 'API unavailable' : runtime.loading ? 'Connecting' : 'Workspace connected'}<span className="avatar small">PO</span></div></header>
      {runtime.data?.demo_mode && <div className="mode-banner"><Icon name="info" size={16} /><span><strong>Demo provider</strong> · Document extraction and message drafting use the explicit offline mock. Decisions still use the rule engine. Use synthetic data only.</span></div>}
      {!runtime.data?.demo_mode && runtime.data && <div className="real-banner">{runtime.data.llm_provider} provider · Document extraction and message drafting enabled · {['outbox', 'manual_outbox'].includes(runtime.data.delivery_mode) ? 'Messages remain in the manual outbox' : runtime.data.delivery_mode}</div>}
      <main className="page-content"><Routes><Route path="/" element={<Dashboard />} /><Route path="/reviews/new" element={<NewReview />} /><Route path="/reviews/:id" element={<Review />} /><Route path="/history" element={<History />} /><Route path="/settings" element={<Settings />} /><Route path="/assumptions" element={<Assumptions />} /><Route path="*" element={<div className="card"><h1>Page not found</h1><Link to="/">Return to overview</Link></div>} /></Routes></main>
      <footer className="app-footer"><span>VendorGate · Vendor onboarding, with a clear audit trail.</span><span>Case study PS-2</span></footer>
    </div>
  </div>;
}

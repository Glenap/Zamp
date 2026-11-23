import React from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

function App() {
  return (
    <main className="min-h-screen bg-slate-50 flex items-center justify-center">
      <h1 className="text-4xl font-semibold tracking-tight text-slate-900">VendorGate</h1>
    </main>
  );
}

const root = document.getElementById('root');
if (!root) throw new Error('VendorGate root element is missing');
createRoot(root).render(<React.StrictMode><App /></React.StrictMode>);

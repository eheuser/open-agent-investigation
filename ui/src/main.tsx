import './index.css';
import App from './App';

// ---- Theme bootstrap -------------------------------------------------
const saved = localStorage.getItem('theme');
if (saved === 'light') {
  document.documentElement.classList.remove('dark');
} else {
  // Default to dark if nothing is stored or the value is "dark"
  document.documentElement.classList.add('dark');
}
// ---------------------------------------------------------------------

import React from 'react';
import { createRoot } from 'react-dom/client';

const container = document.getElementById('root')!;
createRoot(container).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
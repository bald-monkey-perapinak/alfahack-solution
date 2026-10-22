import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { NewsShowcase } from './pages/NewsShowcase';
import './styles/global.css';

createRoot(document.getElementById('root')!).render(<StrictMode><NewsShowcase /></StrictMode>);

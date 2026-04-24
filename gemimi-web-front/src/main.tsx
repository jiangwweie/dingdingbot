import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './components/layout/AppLayout';

import Overview from './pages/runtime/Overview';
import Signals from './pages/runtime/Signals';
import Execution from './pages/runtime/Execution';
import Health from './pages/runtime/Health';

import Candidates from './pages/research/Candidates';
import CandidateDetail from './pages/research/CandidateDetail';
import Replay from './pages/research/Replay';
import Backtests from './pages/research/Backtests';
import Compare from './pages/research/Compare';

import { ErrorBoundary } from './components/layout/ErrorBoundary';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<AppLayout />}>
            <Route index element={<Navigate to="/runtime/overview" replace />} />
            
            <Route path="runtime/overview" element={<Overview />} />
            <Route path="runtime/signals" element={<Signals />} />
            <Route path="runtime/execution" element={<Execution />} />
            <Route path="runtime/health" element={<Health />} />

            <Route path="research/candidates" element={<Candidates />} />
            <Route path="research/candidates/:candidate_name" element={<CandidateDetail />} />
            <Route path="research/replay/:candidate_name" element={<Replay />} />
            <Route path="research/backtests" element={<Backtests />} />
            <Route path="research/compare" element={<Compare />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  </StrictMode>,
);

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './components/layout/AppLayout';

import Overview from './pages/runtime/Overview';
import Portfolio from './pages/runtime/Portfolio';
import Signals from './pages/runtime/Signals';
import Execution from './pages/runtime/Execution';
import Events from './pages/runtime/Events';
import Health from './pages/runtime/Health';

import Candidates from './pages/research/Candidates';
import CandidateDetail from './pages/research/CandidateDetail';
import Replay from './pages/research/Replay';
import ReviewSummary from './pages/research/ReviewSummary';
import Backtests from './pages/research/Backtests';
import Compare from './pages/research/Compare';

import Snapshot from './pages/config/Snapshot';

import { ErrorBoundary } from './components/layout/ErrorBoundary';
import { ThemeProvider } from './components/layout/ThemeContext';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <ThemeProvider defaultTheme="dark" storageKey="trading-console-theme">
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<AppLayout />}>
              <Route index element={<Navigate to="/runtime/overview" replace />} />
              
              <Route path="runtime/overview" element={<Overview />} />
              <Route path="runtime/portfolio" element={<Portfolio />} />
              <Route path="runtime/signals" element={<Signals />} />
              <Route path="runtime/execution" element={<Execution />} />
              <Route path="runtime/events" element={<Events />} />
              <Route path="runtime/health" element={<Health />} />

              <Route path="research/candidates" element={<Candidates />} />
              <Route path="research/candidates/:candidate_name" element={<CandidateDetail />} />
              <Route path="research/replay/:candidate_name" element={<Replay />} />
              <Route path="research/review/:candidate_name" element={<ReviewSummary />} />
              <Route path="research/backtests" element={<Backtests />} />
              <Route path="research/compare" element={<Compare />} />

              <Route path="config/snapshot" element={<Snapshot />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ThemeProvider>
    </ErrorBoundary>
  </StrictMode>,
);

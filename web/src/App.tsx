/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Home from './pages/Home';
import StrategyGroups from './pages/StrategyGroups';
import Intents from './pages/Intents';
import AccountOrders from './pages/AccountOrders';
import Analysis from './pages/Analysis';
import Trace from './pages/Trace';
import { ThemeProvider } from './components/ThemeProvider';

export default function App() {
  return (
    <ThemeProvider defaultTheme="dark">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Navigate to="/home" replace />} />
            <Route path="home" element={<Home />} />
            <Route path="strategy-groups" element={<StrategyGroups />} />
            <Route path="intents" element={<Intents />} />
            <Route path="account-orders" element={<AccountOrders />} />
            <Route path="analysis" element={<Analysis />} />
            <Route path="trace" element={<Trace />} />
            {/* Legacy route catch-all */}
            <Route path="*" element={<Navigate to="/home" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  );
}

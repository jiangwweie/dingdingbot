import React, { useState } from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from './context/ThemeContext';
import { CausalityDrawer } from './components/overview/CausalityDrawer';
import './index.css';

const testQueryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      staleTime: 0,
    },
  },
});

export function RaceTestHarness() {
  const [ticketId, setTicketId] = useState('ticket:ticket-A');

  return (
    <div className="p-4 bg-background min-h-screen text-text-primary">
      <div className="flex gap-2 mb-4 relative z-[90]">
        <button
          id="btn-switch-ticket-a"
          data-testid="btn-switch-ticket-a"
          className="px-3 py-1 bg-surface border border-border rounded text-xs hover:bg-surface-elevated cursor-pointer"
          onClick={() => setTicketId('ticket:ticket-A')}
        >
          Switch to Ticket A
        </button>
        <button
          id="btn-switch-ticket-b"
          data-testid="btn-switch-ticket-b"
          className="px-3 py-1 bg-surface border border-border rounded text-xs hover:bg-surface-elevated cursor-pointer"
          onClick={() => setTicketId('ticket:ticket-B')}
        >
          Switch to Ticket B
        </button>
        <span id="current-harness-ticket" className="text-xs font-mono py-1">
          Current: {ticketId}
        </span>
      </div>

      <CausalityDrawer
        isOpen={true}
        ticketId={ticketId}
        onClose={() => {}}
      />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={testQueryClient}>
      <ThemeProvider>
        <RaceTestHarness />
      </ThemeProvider>
    </QueryClientProvider>
  </React.StrictMode>
);

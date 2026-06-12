import express from 'express';
import path from 'path';
import { createServer as createViteServer } from 'vite';

const PORT = Number(process.env.PORT || 3000);
const READ_MODEL_API_BASE = process.env.TRADING_CONSOLE_API_BASE || 'http://127.0.0.1:8000';
const OPERATOR_SESSION = process.env.TRADING_CONSOLE_OPERATOR_SESSION || '';
const STRATEGY_SIGNAL_SHADOW_PLAN_PATH =
  /^\/api\/trading-console\/strategy-runtimes\/[^/]+\/strategy-signal-shadow-plans$/;
// Allows /api/trading-console/strategy-runtimes/*/live-enablement-mutations only.
const STRATEGY_RUNTIME_LIVE_ENABLEMENT_MUTATION_PATH =
  /^\/api\/trading-console\/strategy-runtimes\/[^/]+\/live-enablement-mutations$/;
const BRC_RUNTIME_DRAFT_FROM_CONFIRMATION_PATH =
  /^\/api\/brc\/strategy-runtime-promotion-confirmations\/[^/]+\/runtime-drafts$/;
const BRC_SHADOW_RUNTIME_LIFECYCLE_PATH =
  /^\/api\/brc\/strategy-runtimes\/[^/]+\/lifecycle$/;

function targetUrl(originalUrl: string): string {
  return new URL(originalUrl, READ_MODEL_API_BASE).toString();
}

function proxyHeaders(headers: express.Request['headers']): HeadersInit {
  const forwarded = new Headers();
  for (const [key, value] of Object.entries(headers)) {
    if (key === 'host' || key === 'content-length') continue;
    if (typeof value === 'string') forwarded.set(key, value);
    else if (Array.isArray(value)) forwarded.set(key, value.join(','));
  }
  if (OPERATOR_SESSION) {
    const existingCookie = forwarded.get('cookie');
    const sessionCookie = `brc_operator_session=${OPERATOR_SESSION}`;
    forwarded.set('cookie', existingCookie ? `${existingCookie}; ${sessionCookie}` : sessionCookie);
  }
  return forwarded;
}

function sendUpstreamHeaders(upstream: Response, res: express.Response) {
  upstream.headers.forEach((value, key) => {
    if (key.toLowerCase() !== 'content-encoding') res.setHeader(key, value);
  });
}

async function proxyJsonRequest(req: express.Request, res: express.Response) {
  try {
    const method = req.method.toUpperCase();
    const upstream = await fetch(targetUrl(req.originalUrl), {
      method,
      headers: proxyHeaders(req.headers),
      body: method === 'GET' || method === 'HEAD' ? undefined : JSON.stringify(req.body ?? {}),
    });
    res.status(upstream.status);
    sendUpstreamHeaders(upstream, res);
    const body = Buffer.from(await upstream.arrayBuffer());
    res.send(body);
  } catch (error) {
    res.status(502).json({
      error: 'trading_console_backend_unavailable',
      message: error instanceof Error ? error.message : String(error),
      upstream: READ_MODEL_API_BASE,
    });
  }
}

async function startServer() {
  const app = express();

  app.use(express.json());

  app.all('/api/auth/*', async (req, res) => {
    const allowed =
      (req.method === 'POST' && (req.path === '/api/auth/login' || req.path === '/api/auth/logout')) ||
      (req.method === 'GET' && req.path === '/api/auth/session');
    if (!allowed) {
      res.status(405).json({
        error: 'trading_console_frontend_auth_proxy_method_not_allowed',
        message: 'Trading Console frontend proxy forwards only login, logout, and session auth requests.',
      });
      return;
    }
    await proxyJsonRequest(req, res);
  });

  app.all('/api/trading-console/*', async (req, res) => {
    const allowedShadowPlanningPost =
      req.method === 'POST' && STRATEGY_SIGNAL_SHADOW_PLAN_PATH.test(req.path);
    const allowedLiveEnablementMutationPost =
      req.method === 'POST' && STRATEGY_RUNTIME_LIVE_ENABLEMENT_MUTATION_PATH.test(req.path);
    if (allowedShadowPlanningPost || allowedLiveEnablementMutationPost) {
      await proxyJsonRequest(req, res);
      return;
    }
    if (req.method !== 'GET') {
      res.status(405).json({
        error: 'trading_console_frontend_proxy_get_only',
        message:
          'Trading Console frontend proxy forwards read-model GET requests plus explicit runtime shadow-plan and live-enablement mutation POSTs only.',
      });
      return;
    }

    try {
      const upstream = await fetch(targetUrl(req.originalUrl), {
        method: 'GET',
        headers: proxyHeaders(req.headers),
      });
      res.status(upstream.status);
      sendUpstreamHeaders(upstream, res);
      const body = Buffer.from(await upstream.arrayBuffer());
      res.send(body);
    } catch (error) {
      res.status(502).json({
        error: 'trading_console_backend_unavailable',
        message: error instanceof Error ? error.message : String(error),
        upstream: READ_MODEL_API_BASE,
      });
    }
  });

  app.all('/api/brc/operations/*', async (req, res) => {
    const allowed =
      req.method === 'POST' &&
      (
        req.path === '/api/brc/operations/preflight' ||
        /^\/api\/brc\/operations\/[^/]+\/confirm$/.test(req.path)
      );
    if (!allowed) {
      res.status(405).json({
        error: 'trading_console_operation_proxy_method_not_allowed',
        message: 'Trading Console forwards only Operation Layer preflight and confirm requests.',
      });
      return;
    }
    await proxyJsonRequest(req, res);
  });

  app.all('/api/brc/strategy-runtime-promotion-confirmations', async (req, res) => {
    if (req.method !== 'GET' && req.method !== 'POST') {
      res.status(405).json({
        error: 'trading_console_promotion_confirmation_proxy_method_not_allowed',
        message: 'Trading Console forwards only promotion confirmation record/list requests.',
      });
      return;
    }
    await proxyJsonRequest(req, res);
  });

  app.all('/api/brc/strategy-runtime-promotion-confirmations/*/runtime-drafts', async (req, res) => {
    if (req.method !== 'POST' || !BRC_RUNTIME_DRAFT_FROM_CONFIRMATION_PATH.test(req.path)) {
      res.status(405).json({
        error: 'trading_console_runtime_draft_proxy_method_not_allowed',
        message: 'Trading Console forwards only confirmed-profile shadow runtime draft creation requests.',
      });
      return;
    }
    await proxyJsonRequest(req, res);
  });

  app.all('/api/brc/strategy-runtimes/*/lifecycle', async (req, res) => {
    if (req.method !== 'POST' || !BRC_SHADOW_RUNTIME_LIFECYCLE_PATH.test(req.path)) {
      res.status(405).json({
        error: 'trading_console_shadow_runtime_lifecycle_proxy_method_not_allowed',
        message: 'Trading Console forwards only shadow runtime lifecycle status requests.',
      });
      return;
    }
    await proxyJsonRequest(req, res);
  });

  app.all('/api/brc/strategy-groups/live-readonly-observation/v1', async (req, res) => {
    if (req.method !== 'GET') {
      res.status(405).json({
        error: 'trading_console_strategy_observation_proxy_method_not_allowed',
        message: 'Trading Console forwards only read-only strategy observation requests.',
      });
      return;
    }
    await proxyJsonRequest(req, res);
  });

  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (_req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Trading Console frontend on http://localhost:${PORT}`);
    console.log(`Read-model API proxy target: ${READ_MODEL_API_BASE}`);
  });
}

startServer();

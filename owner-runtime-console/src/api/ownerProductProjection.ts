import { useEffect, useState } from "react";
import { buildMockProjection, configuredMockScenario } from "../data";
import type { OwnerProductProjection } from "../types";
import { loadOwnerSourceReadinessProjection } from "./ownerSourceReadiness";

export type OwnerProjectionState = {
  data: OwnerProductProjection | null;
  loading: boolean;
  error: string | null;
  refreshedAt: string | null;
};

const defaultEndpoint = "/api/owner-runtime-console/product-projection";

function shouldUseMock() {
  if (typeof window !== "undefined" && new URLSearchParams(window.location.search).has("scenario")) {
    return true;
  }
  return import.meta.env.VITE_OWNER_USE_MOCK === "true";
}

function endpointUrl() {
  return import.meta.env.VITE_OWNER_PRODUCT_PROJECTION_URL || defaultEndpoint;
}

function runtimeMockScenario() {
  if (typeof window !== "undefined") {
    return new URLSearchParams(window.location.search).get("scenario") ?? import.meta.env.VITE_OWNER_MOCK_SCENARIO;
  }
  return import.meta.env.VITE_OWNER_MOCK_SCENARIO;
}

async function loadOwnerProjection(): Promise<OwnerProductProjection> {
  const scenario = configuredMockScenario(runtimeMockScenario());

  if (import.meta.env.VITE_OWNER_SOURCE_READINESS_ENABLED !== "false") {
    return loadOwnerSourceReadinessProjection();
  }

  if (shouldUseMock()) {
    if (scenario === "error") {
      throw new Error("Owner console mock state failed");
    }
    return buildMockProjection(scenario);
  }

  const response = await fetch(endpointUrl(), {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`真实后端不可用：HTTP ${response.status}`);
  }
  return (await response.json()) as OwnerProductProjection;
}

export function useOwnerProductProjection(): OwnerProjectionState {
  const [state, setState] = useState<OwnerProjectionState>({
    data: null,
    loading: true,
    error: null,
    refreshedAt: null,
  });

  useEffect(() => {
    let active = true;

    async function load() {
      setState((current) => ({
        ...current,
        loading: true,
        error: null,
      }));

      try {
        const data = await loadOwnerProjection();
        if (!active) return;
        setState({
          data,
          loading: false,
          error: null,
          refreshedAt: new Date().toISOString(),
        });
      } catch (error) {
        if (!active) return;
        setState({
          data: null,
          loading: false,
          error: error instanceof Error ? error.message : String(error),
          refreshedAt: new Date().toISOString(),
        });
      }
    }

    load();
    return () => {
      active = false;
    };
  }, []);

  return state;
}

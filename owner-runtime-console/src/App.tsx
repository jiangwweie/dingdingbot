import { useEffect, useMemo, useState } from "react";
import { useOwnerProductProjection } from "./api/ownerProductProjection";
import { ErrorState, LoadingState, MobileNav, Sidebar, TopSafetyBar, useThemeMode } from "./console/chrome";
import { type BackendConnectionState, type ConsoleContext, type NavigationKey, selectedStrategyFor } from "./console/model";
import { ConsoleContent } from "./console/pages";

export function App() {
  const { theme, setTheme } = useThemeMode();
  const projectionState = useOwnerProductProjection();
  const [activeView, setActiveView] = useState<NavigationKey>("home");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const summary = projectionState.data?.productSummary ?? null;
  const fundsLocked = projectionState.data?.fundPool.fundsLocked ?? null;
  const connectionState: BackendConnectionState = projectionState.loading
    ? "loading"
    : projectionState.error
      ? "unavailable"
      : "connected";
  const sourceLabel = projectionState.data?.scenario ? `${projectionState.data.source}: ${projectionState.data.scenario}` : projectionState.data?.source;
  const selectedStrategy = useMemo(() => {
    if (!projectionState.data) return null;
    return selectedStrategyFor(projectionState.data, selectedId);
  }, [projectionState.data, selectedId]);
  const context: ConsoleContext = {
    connectionState,
    sourceLabel,
    refreshedAt: projectionState.refreshedAt,
  };

  useEffect(() => {
    if (!projectionState.data) return;
    setSelectedId((current) => current ?? projectionState.data?.selectedStrategyId ?? null);
  }, [projectionState.data]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="flex min-h-screen">
        <Sidebar activeView={activeView} onSelect={setActiveView} />
        <div className="flex min-w-0 flex-1 flex-col">
          <TopSafetyBar connectionState={connectionState} fundsLocked={fundsLocked} setTheme={setTheme} summary={summary} theme={theme} />
          <MobileNav activeView={activeView} onSelect={setActiveView} />
          {projectionState.loading && <LoadingState />}
          {projectionState.error && <ErrorState message={projectionState.error} />}
          {projectionState.data && !projectionState.error && (
            <ConsoleContent
              activeView={activeView}
              context={context}
              onSelect={setSelectedId}
              projection={projectionState.data}
              selectedStrategy={selectedStrategy}
            />
          )}
        </div>
      </div>
    </div>
  );
}

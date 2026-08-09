import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { ownerQueryClient } from "./queryClient";

interface AppProvidersProps {
  children: ReactNode;
}

export function AppProviders({ children }: AppProvidersProps) {
  return <QueryClientProvider client={ownerQueryClient}>{children}</QueryClientProvider>;
}

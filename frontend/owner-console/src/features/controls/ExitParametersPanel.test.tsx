import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { ExitParametersPanel } from "./ExitParametersPanel";
import { getExitParameters, previewExitParameters, publishExitParameters } from "./exitParametersApi";
import type { ExitCurrent, ExitPreview } from "./exitParametersApi";

vi.mock("./exitParametersApi", () => ({getExitParameters:vi.fn(),previewExitParameters:vi.fn(),publishExitParameters:vi.fn()}));
const fixture={ rows:[{event_spec_id:"event_spec:CPM-RO-001:CPM-LONG:v3",binding:{projection_version:1,exit_binding_id:"binding:1"},regime:{revision:1,enabled:false},
  profile:{exit_profile_version:1,position_side:"long",tp1:{reward_multiple:"1",quantity_fraction:"0.5",quantity_rule:null}}}],active_tickets:[],observed_at_ms:1800000000000 } as unknown as ExitCurrent;
function renderPanel(){render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})}><ExitParametersPanel /></QueryClientProvider>);}
beforeEach(()=>{vi.clearAllMocks();vi.mocked(getExitParameters).mockResolvedValue(fixture);vi.mocked(previewExitParameters).mockResolvedValue({profiles:[{exit_profile_version:2,tp1:{reward_multiple:"1",quantity_fraction:"0.05",quantity_rule:{max_actual_fraction:"0.5"}}}],source_profiles:[],quantity_previews:[],affects:"new_tickets_only"} as unknown as ExitPreview);});

it("requires explicit row selection and server preview before any publish",async()=>{
  const user=userEvent.setup();renderPanel();
  await screen.findByText("CPM-RO-001 · LONG");
  expect(publishExitParameters).not.toHaveBeenCalled();
  expect(screen.getByRole("button",{name:"预览所选策略"})).toBeDisabled();
  await user.click(screen.getByRole("button",{name:"填入本次实验方案"}));
  await user.click(screen.getByRole("button",{name:"预览所选策略"}));
  await screen.findByText(/预览通过/);
  expect(previewExitParameters).toHaveBeenCalledWith(expect.objectContaining({changes:[expect.objectContaining({quantity_fraction:"0.05",max_actual_fraction:"0.50",ma50_enabled:true})]}));
  expect(publishExitParameters).not.toHaveBeenCalled();
  expect(screen.getByRole("button",{name:"确认发布新版本"})).toBeDisabled();
});

it("changing a draft invalidates the prior preview",async()=>{
  const user=userEvent.setup();renderPanel();await screen.findByText("CPM-RO-001 · LONG");
  await user.click(screen.getByRole("button",{name:"填入本次实验方案"}));
  await user.click(screen.getByRole("button",{name:"预览所选策略"}));await screen.findByText(/预览通过/);
  await user.clear(screen.getByLabelText("CPM-RO-001 · LONG TP1倍数"));
  expect(screen.queryByRole("button",{name:"确认发布新版本"})).not.toBeInTheDocument();
});

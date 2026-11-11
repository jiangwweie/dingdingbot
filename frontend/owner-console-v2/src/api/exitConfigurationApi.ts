import { apiClient } from './client';
import { apiErrorFromResponse } from './errors';
import type { components } from './schema';
export type ExitConfigurationView = components['schemas']['ExitConfigurationView'];
export type ExitConfigurationIntent = ExitConfigurationView['intent'];
export type ExitConfigurationPreview = components['schemas']['ExitConfigurationPreview'];
export type ExitConfigurationBody = components['schemas']['ExitConfigurationBody'];
export type ExitConfigurationRecord = components['schemas']['ExitConfigurationRecord'];
export async function fetchExitConfiguration() {
  const r=await apiClient.GET('/api/owner/v1/controls/exit-configuration');
  if (!r.response.ok || !r.data) throw apiErrorFromResponse(r.response,r.error);
  return r.data;
}
export async function previewExitConfiguration(intent:ExitConfigurationIntent) {
  const r=await apiClient.POST('/api/owner/v1/controls/exit-configuration/preview',{body:{intent}});
  if (!r.response.ok || !r.data) throw apiErrorFromResponse(r.response,r.error);
  return r.data;
}
export async function activateExitConfiguration(body:ExitConfigurationBody) {
  const r=await apiClient.POST('/api/owner/v1/controls/exit-configuration',{body});
  if (!r.response.ok || !r.data) throw apiErrorFromResponse(r.response,r.error);
  return r.data;
}
export async function fetchExitConfigurationReceipt(key:string) {
  const r=await apiClient.GET('/api/owner/v1/controls/exit-configuration/requests/{idempotency_key}',{params:{path:{idempotency_key:key}}});
  if (!r.response.ok) throw apiErrorFromResponse(r.response,r.error);
  return r.data??null;
}
export type ExitSizingBody = components['schemas']['ExitSizingBody'];
export type ExitSizingView = components['schemas']['ExitSizingView'];
export async function previewExitSizing(body:ExitSizingBody) {
 const r=await apiClient.POST('/api/owner/v1/controls/exit-configuration/sizing-preview',{body});
 if(!r.response.ok||!r.data)throw apiErrorFromResponse(r.response,r.error);
 return r.data;
}

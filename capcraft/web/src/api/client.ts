import type { components } from './schema'

export type Schemas = components['schemas']
export type PlanRequest = Schemas['PlanRequest']
export type PlanResponse = Schemas['PlanResponse']
export type XrayRequest = Schemas['XrayRequest']
export type XrayResponse = Schemas['XrayResponse']
export type DCFRequest = Schemas['DCFRequest']
export type DCFResponse = Schemas['DCFResponse']
export type SampleResponse = Schemas['SampleResponse']
export type Meta = Schemas['Meta']
export type Capabilities = Schemas['Capabilities']
export type CompanyResponse = Schemas['CompanyResponse']
export type RatesResponse = Schemas['RatesResponse']

/** An error the API explained in words (a 422 with a `detail` message). */
export class ApiError extends Error {}

const base = import.meta.env.VITE_API_URL ?? ''

async function request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let res: Response
  try {
    res = await fetch(base + path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    throw new ApiError('Cannot reach the CapCraft server. Start it with: uvicorn capcraft_api.main:app')
  }
  if (!res.ok) {
    let detail = `The server returned ${res.status}.`
    try {
      const j = await res.json()
      if (typeof j.detail === 'string') detail = j.detail
      else if (Array.isArray(j.detail))
        detail = j.detail.map((d: { loc: string[]; msg: string }) => `${d.loc.slice(1).join('.')}: ${d.msg}`).join('; ')
    } catch { /* keep the status message */ }
    throw new ApiError(detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  meta: () => request<Meta>('/api/meta'),
  plan: (b: PlanRequest, s?: AbortSignal) => request<PlanResponse>('/api/plan', b, s),
  xraySample: () => request<SampleResponse>('/api/xray/sample'),
  xray: (b: XrayRequest, s?: AbortSignal) => request<XrayResponse>('/api/xray', b, s),
  dcf: (b: DCFRequest, s?: AbortSignal) => request<DCFResponse>('/api/dcf', b, s),
  capabilities: () => request<Capabilities>('/api/capabilities'),
  company: (ticker: string) => request<CompanyResponse>(`/api/company/${encodeURIComponent(ticker)}`),
  rates: () => request<RatesResponse>('/api/rates'),
}

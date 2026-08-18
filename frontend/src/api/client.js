const API_BASE = import.meta.env.VITE_API_BASE || '/api'

function getToken() {
  return localStorage.getItem('access_token')
}

export function setToken(token) {
  if (token) localStorage.setItem('access_token', token)
  else localStorage.removeItem('access_token')
}

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === 'string' ? detail : JSON.stringify(detail))
    this.status = status
    this.detail = detail
  }
}

async function request(method, path, { body, params, isFormData } = {}) {
  let url = `${API_BASE}${path}`
  if (params) {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
    ).toString()
    if (qs) url += `?${qs}`
  }

  const headers = {}
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  if (body && !isFormData) headers['Content-Type'] = 'application/json'

  const res = await fetch(url, {
    method,
    headers,
    body: isFormData ? body : body ? JSON.stringify(body) : undefined,
  })

  if (res.status === 204) return null

  let data
  const text = await res.text()
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = text
  }

  if (!res.ok) {
    throw new ApiError(res.status, data?.detail || data || res.statusText)
  }
  return data
}

export const api = {
  get: (path, params) => request('GET', path, { params }),
  post: (path, body) => request('POST', path, { body }),
  patch: (path, body) => request('PATCH', path, { body }),
  put: (path, body) => request('PUT', path, { body }),
  postForm: (path, formData) => request('POST', path, { body: formData, isFormData: true }),
}

// ---------- Auth ----------
export const auth = {
  signup: (data) => api.post('/auth/signup', data),
  login: (data) => api.post('/auth/login', data),
}

// ---------- Clients / Engagements ----------
export const clients = {
  list: () => api.get('/clients'),
  create: (data) => api.post('/clients', data),
  get: (id) => api.get(`/clients/${id}`),
}

export const engagements = {
  list: (clientId) => api.get('/engagements', clientId ? { client_id: clientId } : undefined),
  create: (data) => api.post('/engagements', data),
  setMateriality: (id, data) => api.patch(`/engagements/${id}/materiality`, data),
}

// ---------- Data Ingestion / Data Centre ----------
export const dataApi = {
  upload: (engagementId, datasetType, file, onDuplicate = 'ASK') => {
    const fd = new FormData()
    fd.append('dataset_type', datasetType)
    fd.append('file', file)
    fd.append('on_duplicate', onDuplicate)
    return api.postForm(`/engagements/${engagementId}/data/upload`, fd)
  },
  ingestionRuns: (engagementId) => api.get(`/engagements/${engagementId}/data/ingestion-runs`),
  ingestionExceptions: (engagementId, runId) =>
    api.get(`/engagements/${engagementId}/data/ingestion-runs/${runId}/exceptions`),
  trialBalance: (engagementId) => api.get(`/engagements/${engagementId}/data/trial-balance`),
  dataCentre: (engagementId) => api.get(`/engagements/${engagementId}/data-centre`),
}

// ---------- Analytics ----------
export const analytics = {
  mappingSuggestions: (engagementId) => api.get(`/engagements/${engagementId}/trial-balance/mapping-suggestions`),
  applySuggestions: (engagementId, minConfidence) =>
    api.post(`/engagements/${engagementId}/trial-balance/mapping-suggestions/apply`, { min_confidence: minConfidence }),
  approveMapping: (engagementId, accountId, data) =>
    api.patch(`/engagements/${engagementId}/accounts/${accountId}/mapping`, data),
  runTbFlags: (engagementId) => api.post(`/engagements/${engagementId}/analytics/tb-flags/run`),
  runJournalRisk: (engagementId) => api.post(`/engagements/${engagementId}/analytics/journal-risk/run`),
  dashboard: (engagementId) => api.get(`/engagements/${engagementId}/analytics/dashboard`),
}

// ---------- Reconciliation ----------
export const reconciliation = {
  runGst: (engagementId) => api.post(`/engagements/${engagementId}/analytics/gst-reconciliation/run`),
  gstExceptions: (engagementId) => api.get(`/engagements/${engagementId}/gst-reconciliation`),
  runTds: (engagementId) => api.post(`/engagements/${engagementId}/analytics/tds-reconciliation/run`),
  tdsExceptions: (engagementId) => api.get(`/engagements/${engagementId}/tds-reconciliation`),
  runPayroll: (engagementId) => api.post(`/engagements/${engagementId}/analytics/payroll-reconciliation/run`),
  payrollExceptions: (engagementId) => api.get(`/engagements/${engagementId}/payroll-reconciliation`),
  challanMapping: (engagementId, statutoryType) =>
    api.get(`/engagements/${engagementId}/challan-mapping`, { statutory_type: statutoryType }),
  bankReconciliation: (engagementId) => api.get(`/engagements/${engagementId}/bank-reconciliation`),
}

// ---------- AP / AR ----------
export const apAr = {
  duplicateInvoices: (engagementId) => api.get(`/engagements/${engagementId}/ap/duplicate-invoices`),
  apAgeing: (engagementId) => api.get(`/engagements/${engagementId}/ap/ageing`),
  arAgeing: (engagementId) => api.get(`/engagements/${engagementId}/ar/ageing`),
}

// ---------- Fixed Assets / Inventory / Loans / Investments / Intercompany ----------
export const fixedAssets = {
  get: (engagementId) => api.get(`/engagements/${engagementId}/fixed-assets`),
}
export const inventory = {
  get: (engagementId) => api.get(`/engagements/${engagementId}/inventory`),
}
export const loans = {
  get: (engagementId) => api.get(`/engagements/${engagementId}/loans`),
}
export const investments = {
  get: (engagementId) => api.get(`/engagements/${engagementId}/investments`),
}
export const intercompany = {
  get: (engagementId) => api.get(`/engagements/${engagementId}/intercompany`),
}

// ---------- Risk Engine ----------
export const risk = {
  dashboard: (engagementId) => api.get(`/engagements/${engagementId}/risk`),
}

// ---------- Control Tower ----------
export const controlTower = {
  get: (engagementId) => api.get(`/engagements/${engagementId}/control-tower`),
}

// ---------- Pre-Audit Dashboard ----------
export const preAudit = {
  dashboard: (engagementId) => api.get(`/engagements/${engagementId}/pre-audit`),
}

// ---------- Month-End Close ----------
export const monthEndClose = {
  init: (engagementId, period) => api.post(`/engagements/${engagementId}/month-end-close/init?period=${encodeURIComponent(period)}`),
  get: (engagementId, period) => api.get(`/engagements/${engagementId}/month-end-close`, { period }),
  update: (engagementId, taskId, data) => api.patch(`/engagements/${engagementId}/month-end-close/${taskId}`, data),
}

// ---------- Exceptions ----------
export const exceptions = {
  list: (engagementId, filters) => api.get(`/engagements/${engagementId}/exceptions`, filters),
  update: (engagementId, exceptionId, data) => api.patch(`/engagements/${engagementId}/exceptions/${exceptionId}`, data),
  sync: (engagementId) => api.post(`/engagements/${engagementId}/exceptions/sync`),
  rootCause: (engagementId, exceptionId) => api.get(`/engagements/${engagementId}/exceptions/${exceptionId}/root-cause`),
  draftQuery: (engagementId, exceptionId, daysToRespond = 7) =>
    api.post(`/engagements/${engagementId}/exceptions/${exceptionId}/draft-query`, { days_to_respond: daysToRespond }),
}

export const queries = {
  list: (engagementId) => api.get(`/engagements/${engagementId}/queries`),
  respond: (engagementId, queryId, data) => api.patch(`/engagements/${engagementId}/queries/${queryId}`, data),
}

// ---------- CARO / IFC ----------
export const caro = {
  init: (engagementId) => api.post(`/engagements/${engagementId}/caro/init`),
  list: (engagementId) => api.get(`/engagements/${engagementId}/caro`),
  prepare: (engagementId, clauseNo) => api.post(`/engagements/${engagementId}/caro/${clauseNo}/prepare`),
  review: (engagementId, clauseNo) => api.post(`/engagements/${engagementId}/caro/${clauseNo}/review`),
  approve: (engagementId, clauseNo, finalResponse) =>
    api.post(`/engagements/${engagementId}/caro/${clauseNo}/approve`, { final_response: finalResponse }),
}

export const ifc = {
  runAutomated: (engagementId) => api.post(`/engagements/${engagementId}/ifc/run-automated-tests`),
  list: (engagementId) => api.get(`/engagements/${engagementId}/ifc`),
  recordManual: (engagementId, controlId, data) => api.put(`/engagements/${engagementId}/ifc/${controlId}`, data),
}

// ---------- Working Papers ----------
export const workingPapers = {
  autoDraftGst: (engagementId) => api.post(`/engagements/${engagementId}/working-papers/auto-draft/gst`),
  autoDraftTds: (engagementId) => api.post(`/engagements/${engagementId}/working-papers/auto-draft/tds`),
  autoDraftJournalTesting: (engagementId) => api.post(`/engagements/${engagementId}/working-papers/auto-draft/journal-testing`),
  list: (engagementId) => api.get(`/engagements/${engagementId}/working-papers`),
  get: (engagementId, wpId) => api.get(`/engagements/${engagementId}/working-papers/${wpId}`),
  prepare: (engagementId, wpId) => api.post(`/engagements/${engagementId}/working-papers/${wpId}/prepare`),
  review: (engagementId, wpId) => api.post(`/engagements/${engagementId}/working-papers/${wpId}/review`),
  approve: (engagementId, wpId, finalConclusion) =>
    api.post(`/engagements/${engagementId}/working-papers/${wpId}/approve`, { final_conclusion: finalConclusion }),
}

// ---------- AI Assistant ----------
export const aiAssistant = {
  ask: (engagementId, question) => api.post(`/engagements/${engagementId}/ai-assistant/ask`, { question }),
}

// ---------- Disclosure Checklist / Export ----------
export const disclosureChecklist = {
  get: (engagementId) => api.get(`/engagements/${engagementId}/disclosure-checklist`),
}

export async function downloadAuditFile(engagementId, financialYear) {
  // The export endpoint (built in the Audit Module, Phase 12) only reads
  // auth from the Authorization header via HTTPBearer — a plain <a href>
  // link can't attach that header, and a ?token= query param wouldn't
  // actually be read by the backend. Fetching as a blob with the header
  // set explicitly, then triggering a client-side download, works without
  // touching the working backend endpoint at all.
  const token = getToken()
  const res = await fetch(`${API_BASE}/engagements/${engagementId}/export/audit-file.xlsx`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new ApiError(res.status, await res.text())
  const blob = await res.blob()
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `audit-file-${financialYear || 'export'}.xlsx`
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

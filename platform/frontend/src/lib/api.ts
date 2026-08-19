import type {
  ActiveDeployment,
  Application,
  AvailableActions,
  Backup,
  DeploymentPlan,
  Envelope,
  HostState,
  ImportResult,
  Operation,
  OperationEvent,
  OperationLogEntry,
  PlatformErrorBody,
  PortSuggestions,
  ReconciliationResult,
  Release,
  ScanResult,
  VerificationResult,
} from "@/types/api"

/** Thrown for every real `PlatformError` the backend returns — carries
 * the full structured error object (§8 Platform Error Contract) so
 * `ErrorPresentation` can render code/message/details without ever
 * showing a raw exception.
 */
export class PlatformApiError extends Error {
  body: PlatformErrorBody

  constructor(body: PlatformErrorBody) {
    super(body.message)
    this.body = body
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  })
  const envelope = (await response.json()) as Envelope<T>
  if (!envelope.success || envelope.error) {
    throw new PlatformApiError(
      envelope.error ?? {
        code: "PLT-INTERNAL-001",
        category: "INTERNAL",
        message: "The request failed for an unknown reason.",
        stage: null,
        retryable: false,
        details: {},
        request_id: envelope.request_id,
        operation_id: null,
        log_reference: null,
      }
    )
  }
  return envelope.data as T
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined })
}

export const api = {
  // Health
  health: () => request<{ status: string; checks: Record<string, string> }>("/health/ready"),

  // Operations
  listOperations: (status?: string, limit = 50) =>
    request<{ items: Operation[] }>(
      `/operations?limit=${limit}${status ? `&status=${status}` : ""}`
    ),
  getOperation: (operationId: string) => request<Operation>(`/operations/${operationId}`),
  getOperationEvents: (operationId: string) =>
    request<{ events: OperationEvent[] }>(`/operations/${operationId}/events`),
  getOperationLogs: (operationId: string) =>
    request<{ logs: OperationLogEntry[] }>(`/operations/${operationId}/logs`),

  // Release discovery / import
  scanReleaseCandidates: () => post<ScanResult>("/release-candidates/scan"),
  listReleaseCandidates: () => request<{ items: ScanResult["candidates"] }>("/release-candidates"),
  importReleaseCandidate: (candidateId: string, requestedBy: string) =>
    post<ImportResult>(`/release-candidates/${candidateId}/import`, { requested_by: requestedBy }),

  // Applications / releases
  listApplications: () => request<{ items: Application[] }>("/applications"),
  getApplication: (applicationId: string) => request<Application>(`/applications/${applicationId}`),
  listApplicationReleases: (applicationId: string) =>
    request<{ items: Release[] }>(`/applications/${applicationId}/releases`),
  getRelease: (releaseId: string) => request<Release>(`/releases/${releaseId}`),
  getActiveDeployment: (applicationId: string) =>
    request<ActiveDeployment | null>(`/applications/${applicationId}/active-deployment`),
  getAvailableActions: (applicationId: string, targetReleaseId?: string) =>
    request<AvailableActions>(
      `/applications/${applicationId}/actions${targetReleaseId ? `?target_release_id=${targetReleaseId}` : ""}`
    ),

  // Planning
  prepareInstallation: (releaseId: string) => post<DeploymentPlan>(`/releases/${releaseId}/installation-plan`),
  prepareUpdate: (applicationId: string, targetReleaseId: string) =>
    post<DeploymentPlan>(`/applications/${applicationId}/update-plan`, { target_release_id: targetReleaseId }),
  suggestPorts: (count = 1) => post<PortSuggestions>("/host/ports/suggestions", { count }),

  // Install / Update
  installRelease: (
    releaseId: string,
    configuration: Record<string, { value: unknown }>,
    requestedBy: string
  ) => post<Operation>(`/releases/${releaseId}/install`, { configuration, requested_by: requestedBy }),
  updateApplication: (
    applicationId: string,
    targetReleaseId: string,
    configurationOverrides: Record<string, { value: unknown }>,
    requestedBy: string
  ) =>
    post<Operation>(`/applications/${applicationId}/update`, {
      target_release_id: targetReleaseId,
      configuration_overrides: configurationOverrides,
      requested_by: requestedBy,
    }),

  // Verification / host state / reconciliation
  verifyDeployment: (applicationId: string, requestedBy: string) =>
    post<VerificationResult>(`/applications/${applicationId}/verify`, { requested_by: requestedBy }),
  getVerificationResult: (verificationRunId: string) =>
    request<VerificationResult>(`/verifications/${verificationRunId}`),
  getHostState: (applicationId: string) => request<HostState>(`/applications/${applicationId}/host-state`),
  reconcile: (applicationId: string) =>
    post<ReconciliationResult>(`/applications/${applicationId}/reconcile`, {}),

  // Backups
  createBackup: (applicationId: string, requestedBy: string) =>
    post<Operation>(`/applications/${applicationId}/backups`, { requested_by: requestedBy }),
  listBackups: (applicationId: string) => request<{ items: Backup[] }>(`/applications/${applicationId}/backups`),
  getBackup: (backupId: string) => request<Backup>(`/backups/${backupId}`),

  // Recovery
  restoreBackup: (applicationId: string, backupId: string, requestedBy: string) =>
    post<Operation>(`/backups/${backupId}/restore`, { application_id: applicationId, requested_by: requestedBy }),
  recoverApplication: (
    applicationId: string,
    failedOperationId: string,
    backupId: string,
    requestedBy: string
  ) =>
    post<Operation>(`/applications/${applicationId}/recover`, {
      failed_operation_id: failedOperationId,
      backup_id: backupId,
      requested_by: requestedBy,
    }),
}

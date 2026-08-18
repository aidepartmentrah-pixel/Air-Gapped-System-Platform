// Mirrors the Platform's real API response shapes — see
// platform/src/rah_platform/envelope.py (§5.2 common response envelope)
// and the individual result shapes each module actually returns. Kept
// intentionally close to what the backend really sends, not the
// architecture's aspirational shapes, since this is what the UI
// actually consumes.

export interface PlatformErrorBody {
  code: string
  category: string
  message: string
  stage: string | null
  retryable: boolean
  details: Record<string, unknown>
  request_id: string | null
  operation_id: string | null
  log_reference: string | null
}

export interface Envelope<T> {
  success: boolean
  data: T | null
  warnings: string[]
  error: PlatformErrorBody | null
  request_id: string
  timestamp: string
}

export interface OperationLinks {
  events: string
  logs: string
}

export interface Operation {
  operation_id: string
  operation_type: string
  application_id: string
  status: "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED"
  stage: string | null
  requested_by: string
  error: PlatformErrorBody | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  links: OperationLinks
}

export interface OperationEvent {
  sequence: number
  event_type: string
  status: string
  message: string
  details: Record<string, unknown> | null
  occurred_at: string
}

export interface OperationLogEntry {
  sequence: number
  level: string
  message: string
  details: Record<string, unknown> | null
  occurred_at: string
}

export interface ActiveDeployment {
  deployment_id: string
  release_id: string
  version: string
  deployed_at: string
  verification_status: string | null
}

export interface Application {
  id: string
  slug: string
  name: string
  description: string | null
  canonical_path: string | null
  compose_project_name: string | null
  active_deployment: ActiveDeployment | null
  operational_health: "NOT_INSTALLED" | "UNKNOWN" | "HEALTHY" | "UNHEALTHY"
  available_release_count: number
}

export interface SupportedOperations {
  fresh_install: boolean
  update: boolean
  downgrade: boolean
  reinstall: boolean
}

export interface Release {
  id: string
  application_id: string
  version: string
  summary: string | null
  created_at_engineering: string | null
  imported_at: string
  contract_version: string
  manifest_schema_version: string
  storage_state: string
  release_fingerprint: string
  supported_operations: SupportedOperations
  deployment_state: "ACTIVE" | "PREVIOUSLY_DEPLOYED" | "NEVER_DEPLOYED" | "REMOVED_FROM_STORAGE"
}

export interface BlockingReason {
  code: string
  message: string
}

export interface ActionAvailability {
  action: string
  allowed: boolean
  blocking_reasons: BlockingReason[]
  requirements: string[]
}

export interface AvailableActions {
  application_id: string
  active_release: { id: string; version: string } | null
  target_release: { id: string; version: string } | null
  actions: ActionAvailability[]
}

export interface ReleaseCandidate {
  candidate_id: string
  directory_name: string
  application_slug: string | null
  release_version: string | null
  discovery_state: string
  already_imported: boolean
  issues: { code: string; message: string }[]
  first_seen_at: string
  last_scanned_at: string
}

export interface ScanResult {
  candidate_count: number
  candidates: ReleaseCandidate[]
}

export interface ImportResult {
  release_id: string
  application: { id: string; slug: string }
}

export interface ConfigurationInputDescriptor {
  key: string
  label: string
  type: string
  required: boolean
  secret: boolean
  source: string
  current_value?: unknown
  value_state?: string
}

export interface DeploymentPlan {
  plan_id: string
  operation_type: "INSTALL" | "UPDATE"
  application: { id: string; slug: string }
  source_release: { id: string; version: string } | null
  target_release: { id: string; version: string }
  allowed: boolean
  blocking_issues: BlockingReason[]
  canonical_path: string
  compose_project_name: string
  configuration_inputs: ConfigurationInputDescriptor[]
  expected_services: string[]
  backup: { required: boolean; supported: boolean }
  database_migration: { required: boolean; target_schema_version: string | null }
  verification_checks: string[]
}

export interface PortSuggestions {
  suggestions: number[]
  provisional: boolean
}

export interface VerificationCheck {
  check_key: string
  status: string
  message: string
  evidence: Record<string, unknown>
}

export interface VerificationSummary {
  passed: number
  failed: number
  not_applicable: number
  not_executed: number
}

export interface VerificationResult {
  verification_run_id: string
  application_id: string
  expected_release_id: string
  verification_type: string
  status: string
  started_at: string
  completed_at: string | null
  checks: VerificationCheck[]
  summary: VerificationSummary
}

export interface Backup {
  backup_id: string
  operation_id: string
  application_id: string
  deployment_id: string | null
  backup_type: string
  storage_path: string
  checksum: string | null
  status: string
  verified: boolean
  verified_at: string | null
  created_at: string
  notes: string | null
}

export interface ReconciliationResult {
  application_id: string
  recorded_release: string | null
  observed_release: string | null
  status: "UNKNOWN" | "CONSISTENT" | "PARTIALLY_RUNNING" | "DRIFT_DETECTED" | "UNREACHABLE"
  drift_items: { type: string; message?: string; [key: string]: unknown }[]
  recorded_at: string
}

export interface HostContainerState {
  service: string
  expected_image: string
  observed_image: string | null
  state: string
  healthy: boolean
}

export interface HostState {
  application_id: string
  observed_at: string
  deployment_path: { expected: string | null; exists: boolean }
  compose: { expected_project: string | null; observed_project: string | null; matches: boolean }
  containers: HostContainerState[]
  ports: { port: number; expected: boolean; listening: boolean }[]
}

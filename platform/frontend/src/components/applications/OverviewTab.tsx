import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { ShieldCheck, Archive, RefreshCw } from "lucide-react"
import { api, PlatformApiError } from "@/lib/api"
import type { Application, PlatformErrorBody } from "@/types/api"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ErrorPresentation } from "@/components/operations/ErrorPresentation"
import { ProgressView } from "@/components/operations/ProgressView"

function healthBadge(health: Application["operational_health"]) {
  const map: Record<Application["operational_health"], { label: string; className: string }> = {
    NOT_INSTALLED: { label: "Not Installed", className: "text-muted-foreground" },
    UNKNOWN: { label: "Unknown", className: "border-warning/40 text-warning" },
    HEALTHY: { label: "Healthy", className: "border-success/40 text-success" },
    UNHEALTHY: { label: "Unhealthy", className: "border-destructive/40 text-destructive" },
  }
  const entry = map[health]
  return (
    <Badge variant="outline" className={entry.className}>
      {entry.label}
    </Badge>
  )
}

export function OverviewTab({ application }: { application: Application }) {
  const queryClient = useQueryClient()
  const [error, setError] = useState<PlatformErrorBody | null>(null)
  const [activeOperationId, setActiveOperationId] = useState<string | null>(null)

  const { data: releases } = useQuery({
    queryKey: ["application-releases", application.id],
    queryFn: () => api.listApplicationReleases(application.id),
  })
  const { data: recentOps } = useQuery({
    queryKey: ["operations", "recent-for-app"],
    queryFn: () => api.listOperations(undefined, 20),
  })

  const verify = useMutation({
    mutationFn: () => api.verifyDeployment(application.id, "operator:ui"),
    onSuccess: () => {
      setError(null)
      queryClient.invalidateQueries({ queryKey: ["application", application.id] })
      // "operations" (no further key segments) matches every operations
      // list query by prefix — Recent Operations here, History's own
      // list, and the Dashboard's — so a real Verify/Backup always shows
      // up immediately, not just after an unrelated refetch.
      queryClient.invalidateQueries({ queryKey: ["operations"] })
    },
    onError: (err) => setError(err instanceof PlatformApiError ? err.body : null),
  })

  const backup = useMutation({
    mutationFn: () => api.createBackup(application.id, "operator:ui"),
    onSuccess: (operation) => {
      setError(null)
      queryClient.invalidateQueries({ queryKey: ["operations"] })
      setActiveOperationId(operation.operation_id)
    },
    onError: (err) => setError(err instanceof PlatformApiError ? err.body : null),
  })

  const latest = releases?.items.at(-1)
  const forThisApp = (recentOps?.items ?? []).filter((op) => op.application_id === application.id).slice(0, 5)

  return (
    <div className="grid grid-cols-3 gap-4">
      <Card className="col-span-2 space-y-4 p-5">
        <h3 className="text-base font-semibold">General Information</h3>
        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-xs text-muted-foreground">Slug</dt>
            <dd className="font-mono">{application.slug}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Available Releases</dt>
            <dd>{application.available_release_count}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Current Installation</dt>
            <dd>{application.active_deployment ? application.active_deployment.version : "Not installed"}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Health</dt>
            <dd>{healthBadge(application.operational_health)}</dd>
          </div>
        </dl>

        {error && <ErrorPresentation error={error} />}
        {activeOperationId && (
          <ProgressView
            operationId={activeOperationId}
            onDone={() => queryClient.invalidateQueries({ queryKey: ["applications"] })}
          />
        )}

        <div className="flex flex-wrap gap-2 border-t border-border pt-4">
          {!application.active_deployment && latest && (
            <Button asChild size="sm">
              <Link to="/applications/$applicationId/install" params={{ applicationId: application.id }} search={{ releaseId: latest.id }}>
                Install
              </Link>
            </Button>
          )}
          {application.active_deployment &&
            latest &&
            latest.version !== application.active_deployment.version &&
            latest.supported_operations.update && (
              <Button asChild size="sm">
                <Link to="/applications/$applicationId/update" params={{ applicationId: application.id }} search={{ releaseId: latest.id }}>
                  Update
                </Link>
              </Button>
            )}
          {application.active_deployment && (
            <Button size="sm" variant="outline" className="gap-1.5" disabled={verify.isPending} onClick={() => verify.mutate()}>
              <ShieldCheck className="size-4" />
              Verify
            </Button>
          )}
          {application.active_deployment && (
            <Button size="sm" variant="outline" className="gap-1.5" disabled={backup.isPending} onClick={() => backup.mutate()}>
              <Archive className="size-4" />
              Backup
            </Button>
          )}
        </div>
      </Card>

      <Card className="space-y-3 p-5">
        <h3 className="flex items-center gap-1.5 text-base font-semibold">
          <RefreshCw className="size-4" />
          Recent Operations
        </h3>
        {forThisApp.length === 0 ? (
          <p className="text-sm text-muted-foreground">No operations yet.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {forThisApp.map((op) => (
              <li key={op.operation_id} className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">{op.operation_type}</span>
                <Badge
                  variant="outline"
                  className={
                    op.status === "SUCCEEDED"
                      ? "border-success/40 text-success"
                      : op.status === "FAILED"
                        ? "border-destructive/40 text-destructive"
                        : "border-primary/40 text-primary"
                  }
                >
                  {op.status}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}

import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { Archive } from "lucide-react"
import { api, PlatformApiError } from "@/lib/api"
import type { PlatformErrorBody } from "@/types/api"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { ErrorPresentation } from "@/components/operations/ErrorPresentation"
import { ProgressView } from "@/components/operations/ProgressView"

export function UpdateFlow({ applicationId, releaseId }: { applicationId: string; releaseId: string }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [overrides, setOverrides] = useState<Record<string, unknown>>({})
  const [error, setError] = useState<PlatformErrorBody | null>(null)
  const [operationId, setOperationId] = useState<string | null>(null)

  const { data: plan } = useQuery({
    queryKey: ["update-plan", applicationId, releaseId],
    queryFn: () => api.prepareUpdate(applicationId, releaseId),
  })

  const update = useMutation({
    mutationFn: () => {
      const configuration_overrides: Record<string, { value: unknown }> = {}
      for (const [key, value] of Object.entries(overrides)) {
        if (value !== undefined && value !== "") configuration_overrides[key] = { value }
      }
      return api.updateApplication(applicationId, releaseId, configuration_overrides, "operator:ui")
    },
    onSuccess: (operation) => {
      setError(null)
      setOperationId(operation.operation_id)
    },
    onError: (err) => setError(err instanceof PlatformApiError ? err.body : null),
  })

  if (!plan) {
    return <div className="text-sm text-muted-foreground">Loading update plan…</div>
  }

  if (operationId) {
    return (
      <div className="max-w-2xl space-y-4">
        <h1 className="text-2xl font-semibold">Updating {plan.application.slug}</h1>
        <ProgressView
          operationId={operationId}
          onDone={(status) => {
            queryClient.invalidateQueries({ queryKey: ["applications"] })
            queryClient.invalidateQueries({ queryKey: ["application", applicationId] })
            queryClient.invalidateQueries({ queryKey: ["operations"] })
            if (status === "SUCCEEDED") {
              setTimeout(() => navigate({ to: "/applications/$applicationId", params: { applicationId } }), 1500)
            }
          }}
        />
      </div>
    )
  }

  const editableInputs = plan.configuration_inputs.filter((i) => i.source === "operator")

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Update {plan.application.slug}</h1>
        <p className="text-sm text-muted-foreground">
          {plan.source_release?.version} → {plan.target_release.version}
        </p>
      </div>

      {!plan.allowed && (
        <Card className="border-warning/40 bg-warning/5 p-4">
          <p className="text-sm font-medium text-warning">This update cannot proceed yet</p>
          <ul className="mt-1.5 list-inside list-disc text-sm text-muted-foreground">
            {plan.blocking_issues.map((issue) => (
              <li key={issue.code}>{issue.message}</li>
            ))}
          </ul>
        </Card>
      )}

      {plan.backup.required && (
        <Card className="flex items-center gap-3 border-primary/30 bg-primary/5 p-4">
          <Archive className="size-4 text-primary" />
          <p className="text-sm">
            A backup is <span className="font-medium">required</span> before this update and will be taken automatically.
          </p>
        </Card>
      )}

      <Card className="space-y-4 p-5">
        <h3 className="text-sm font-semibold text-muted-foreground">Configuration</h3>
        {editableInputs.map((input) => (
          <div key={input.key} className="space-y-1.5">
            <Label htmlFor={input.key}>{input.label}</Label>
            {input.value_state === "PRESERVED" || input.current_value !== undefined ? (
              <p className="text-xs text-muted-foreground">
                Preserved from the current deployment — leave blank to keep it.
              </p>
            ) : null}
            <Input
              id={input.key}
              type={input.secret ? "password" : "text"}
              placeholder={input.secret ? "(preserved)" : String(input.current_value ?? "")}
              value={(overrides[input.key] as string | undefined) ?? ""}
              onChange={(e) => setOverrides((v) => ({ ...v, [input.key]: e.target.value }))}
            />
          </div>
        ))}
        {plan.database_migration.required && (
          <div className="flex items-center justify-between border-t border-border pt-3 text-sm">
            <span className="text-muted-foreground">Database migration</span>
            <Badge variant="outline">target schema {plan.database_migration.target_schema_version}</Badge>
          </div>
        )}
      </Card>

      {error && <ErrorPresentation error={error} onRetry={() => update.mutate()} />}

      <div className="flex justify-end">
        <Button disabled={!plan.allowed || update.isPending} onClick={() => update.mutate()}>
          {update.isPending ? "Updating…" : "Update"}
        </Button>
      </div>
    </div>
  )
}

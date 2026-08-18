import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { ArrowLeft, ArrowRight, Wand2 } from "lucide-react"
import { api, PlatformApiError } from "@/lib/api"
import type { PlatformErrorBody } from "@/types/api"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { ErrorPresentation } from "@/components/operations/ErrorPresentation"
import { ProgressView } from "@/components/operations/ProgressView"

const STEPS = ["Installation Location", "Port Selection", "Configuration", "Review & Install"] as const

export function InstallWizard({ applicationId, releaseId }: { applicationId: string; releaseId: string }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [step, setStep] = useState(0)
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [error, setError] = useState<PlatformErrorBody | null>(null)
  const [operationId, setOperationId] = useState<string | null>(null)

  const { data: plan } = useQuery({
    queryKey: ["installation-plan", releaseId],
    queryFn: () => api.prepareInstallation(releaseId),
  })

  const suggestPorts = useMutation({
    mutationFn: () => api.suggestPorts(1),
  })

  const install = useMutation({
    mutationFn: () => {
      const configuration: Record<string, { value: unknown }> = {}
      for (const [key, value] of Object.entries(values)) {
        if (value !== undefined && value !== "") configuration[key] = { value }
      }
      return api.installRelease(releaseId, configuration, "operator:ui")
    },
    onSuccess: (operation) => {
      setError(null)
      setOperationId(operation.operation_id)
    },
    onError: (err) => setError(err instanceof PlatformApiError ? err.body : null),
  })

  if (!plan) {
    return <div className="text-sm text-muted-foreground">Loading installation plan…</div>
  }

  const portInputs = plan.configuration_inputs.filter((i) => i.type === "port")
  const otherInputs = plan.configuration_inputs.filter((i) => i.type !== "port")

  if (operationId) {
    return (
      <div className="max-w-2xl space-y-4">
        <h1 className="text-2xl font-semibold">Installing {plan.application.slug}</h1>
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

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Install {plan.application.slug}</h1>
        <p className="text-sm text-muted-foreground">
          Target Release <span className="font-mono">{plan.target_release.version}</span>
        </p>
      </div>

      <div className="flex items-center gap-2">
        {STEPS.map((label, index) => (
          <div key={label} className="flex items-center gap-2">
            <div
              className={
                "flex size-6 items-center justify-center rounded-full text-xs font-medium " +
                (index === step
                  ? "bg-primary text-primary-foreground"
                  : index < step
                    ? "bg-success text-white"
                    : "bg-muted text-muted-foreground")
              }
            >
              {index + 1}
            </div>
            {index < STEPS.length - 1 && <div className="h-px w-8 bg-border" />}
          </div>
        ))}
      </div>
      <div className="text-sm font-medium text-muted-foreground">{STEPS[step]}</div>

      {error && <ErrorPresentation error={error} onRetry={() => install.mutate()} />}

      {step === 0 && (
        <Card className="space-y-3 p-5 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Canonical Path</span>
            <span className="font-mono">{plan.canonical_path}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Compose Project</span>
            <span className="font-mono">{plan.compose_project_name}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Services</span>
            <span>{plan.expected_services.join(", ")}</span>
          </div>
        </Card>
      )}

      {step === 1 && (
        <Card className="space-y-4 p-5">
          {portInputs.length === 0 && <p className="text-sm text-muted-foreground">This Release declares no ports.</p>}
          {portInputs.map((input) => (
            <div key={input.key} className="space-y-1.5">
              <Label htmlFor={input.key}>{input.label}</Label>
              <div className="flex gap-2">
                <Input
                  id={input.key}
                  type="number"
                  value={(values[input.key] as number | undefined) ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [input.key]: Number(e.target.value) }))}
                />
                <Button
                  type="button"
                  variant="outline"
                  className="gap-1.5 whitespace-nowrap"
                  disabled={suggestPorts.isPending}
                  onClick={async () => {
                    const result = await suggestPorts.mutateAsync()
                    if (result.suggestions[0]) setValues((v) => ({ ...v, [input.key]: result.suggestions[0] }))
                  }}
                >
                  <Wand2 className="size-3.5" />
                  Suggest
                </Button>
              </div>
            </div>
          ))}
        </Card>
      )}

      {step === 2 && (
        <Card className="space-y-4 p-5">
          {otherInputs.length === 0 && <p className="text-sm text-muted-foreground">No further configuration required.</p>}
          {otherInputs.map((input) => (
            <div key={input.key} className="space-y-1.5">
              <Label htmlFor={input.key}>
                {input.label} {input.required && <span className="text-destructive">*</span>}
              </Label>
              <Input
                id={input.key}
                type={input.secret ? "password" : "text"}
                value={(values[input.key] as string | undefined) ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [input.key]: e.target.value }))}
              />
            </div>
          ))}
        </Card>
      )}

      {step === 3 && (
        <Card className="space-y-3 p-5 text-sm">
          <h3 className="font-semibold">Review</h3>
          {plan.configuration_inputs.map((input) => (
            <div key={input.key} className="flex justify-between border-b border-border pb-2 last:border-0">
              <span className="text-muted-foreground">{input.label}</span>
              <span className="font-mono">
                {input.secret ? (values[input.key] ? "••••••••" : "—") : String(values[input.key] ?? input.current_value ?? "—")}
              </span>
            </div>
          ))}
          <div className="flex justify-between pt-1">
            <span className="text-muted-foreground">Verification</span>
            <Badge variant="outline">{plan.verification_checks.length} checks</Badge>
          </div>
        </Card>
      )}

      <div className="flex justify-between">
        <Button variant="outline" className="gap-1.5" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>
          <ArrowLeft className="size-4" />
          Back
        </Button>
        {step < STEPS.length - 1 ? (
          <Button className="gap-1.5" onClick={() => setStep((s) => s + 1)}>
            Next
            <ArrowRight className="size-4" />
          </Button>
        ) : (
          <Button disabled={install.isPending} onClick={() => install.mutate()}>
            {install.isPending ? "Installing…" : "Install"}
          </Button>
        )}
      </div>
    </div>
  )
}

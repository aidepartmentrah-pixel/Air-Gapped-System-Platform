import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { Application } from "@/types/api"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"

export function SettingsTab({ application }: { application: Application }) {
  const activeReleaseId = application.active_deployment?.release_id

  // There is no standalone "edit configuration" capability in Period A
  // — configuration only changes through a real Update (§7.15
  // Configuration Preservation Rule ties config to deployments, not a
  // freestanding mutable settings store). Reusing `prepare_update`
  // against the application's own active Release is a real, honest way
  // to surface the *actual* current values (it always computes
  // `configuration_inputs` from the real Registry, even though
  // `target == active` makes the plan itself `blocked`) rather than
  // fabricating an editable form backed by nothing.
  const { data: plan } = useQuery({
    queryKey: ["settings-plan", application.id, activeReleaseId],
    queryFn: () => api.prepareUpdate(application.id, activeReleaseId as string),
    enabled: !!activeReleaseId,
  })

  if (!activeReleaseId) {
    return (
      <Card className="p-8 text-center text-sm text-muted-foreground">
        Settings become available once this application is installed.
      </Card>
    )
  }

  return (
    <Card className="space-y-5 p-5">
      <div>
        <h3 className="text-base font-semibold">Configuration</h3>
        <p className="text-sm text-muted-foreground">
          Current deployment configuration, ports and secrets. Values are changed through Update, not edited here directly.
        </p>
      </div>

      <div className="space-y-3">
        {(plan?.configuration_inputs ?? []).map((input) => (
          <div key={input.key} className="flex items-center justify-between border-b border-border pb-3 last:border-0">
            <div>
              <div className="text-sm font-medium">{input.label}</div>
              <div className="text-xs text-muted-foreground">
                {input.key} · {input.type}
              </div>
            </div>
            <div className="text-sm">
              {input.secret ? (
                <Badge variant="outline" className="text-muted-foreground">
                  {input.value_state === "PRESERVED" ? "Secret set" : "Not set"}
                </Badge>
              ) : (
                <span className="font-mono">{String(input.current_value ?? "—")}</span>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="flex gap-2 border-t border-border pt-4">
        <Button size="sm" disabled>
          Save
        </Button>
        <Button size="sm" variant="outline" disabled>
          Reset
        </Button>
      </div>
    </Card>
  )
}

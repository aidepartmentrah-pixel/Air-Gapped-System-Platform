import { useQuery } from "@tanstack/react-query"
import { CheckCircle2, XCircle, ShieldCheck, ArrowUpCircle, PackagePlus, LifeBuoy } from "lucide-react"
import { api } from "@/lib/api"
import type { Application } from "@/types/api"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

const TYPE_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  INSTALL: PackagePlus,
  UPDATE: ArrowUpCircle,
  VERIFY: ShieldCheck,
  RECOVER: LifeBuoy,
}

const TYPE_LABEL: Record<string, string> = {
  INSTALL: "Installed",
  UPDATE: "Updated",
  VERIFY: "Verified",
  BACKUP: "Backed up",
  RECOVER: "Recovered",
  RESTORE: "Restored",
}

export function HistoryTab({ application }: { application: Application }) {
  const { data } = useQuery({
    queryKey: ["operations", "history", application.id],
    queryFn: () => api.listOperations(undefined, 100),
  })

  const items = (data?.items ?? []).filter((op) => op.application_id === application.id)

  return (
    <Card className="p-5">
      <h3 className="mb-4 text-base font-semibold">History</h3>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No history yet.</p>
      ) : (
        <ol className="space-y-4 border-l border-border pl-4">
          {items.map((op) => {
            const Icon = TYPE_ICON[op.operation_type] ?? PackagePlus
            const failed = op.status === "FAILED"
            return (
              <li key={op.operation_id} className="relative">
                <span
                  className={
                    "absolute -left-[21px] flex size-4 items-center justify-center rounded-full " +
                    (failed ? "bg-destructive" : op.status === "SUCCEEDED" ? "bg-success" : "bg-muted-foreground")
                  }
                >
                  {failed ? (
                    <XCircle className="size-3 text-white" />
                  ) : op.status === "SUCCEEDED" ? (
                    <CheckCircle2 className="size-3 text-white" />
                  ) : null}
                </span>
                <div className="flex items-center gap-2">
                  <Icon className="size-4 text-muted-foreground" />
                  <span className="text-sm font-medium">{TYPE_LABEL[op.operation_type] ?? op.operation_type}</span>
                  <Badge
                    variant="outline"
                    className={
                      failed
                        ? "border-destructive/40 text-destructive"
                        : op.status === "SUCCEEDED"
                          ? "border-success/40 text-success"
                          : "border-primary/40 text-primary"
                    }
                  >
                    {op.status}
                  </Badge>
                </div>
                <div className="text-xs text-muted-foreground">
                  {new Date(op.created_at).toLocaleString()} · {op.requested_by}
                </div>
                {failed && op.error && <div className="mt-1 text-xs text-destructive">{op.error.message}</div>}
              </li>
            )
          })}
        </ol>
      )}
    </Card>
  )
}

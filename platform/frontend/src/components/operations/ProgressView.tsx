import { useEffect, useRef, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { CheckCircle2, ChevronDown, ChevronRight, Loader2, XCircle } from "lucide-react"
import { api } from "@/lib/api"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { ErrorPresentation } from "@/components/operations/ErrorPresentation"

const TERMINAL = new Set(["SUCCEEDED", "FAILED", "CANCELLED"])

function statusBadge(status: string) {
  if (status === "SUCCEEDED")
    return (
      <Badge variant="outline" className="gap-1.5 border-success/40 text-success">
        <CheckCircle2 className="size-3.5" />
        Completed
      </Badge>
    )
  if (status === "FAILED")
    return (
      <Badge variant="outline" className="gap-1.5 border-destructive/40 text-destructive">
        <XCircle className="size-3.5" />
        Failed
      </Badge>
    )
  if (status === "RUNNING")
    return (
      <Badge variant="outline" className="gap-1.5 border-primary/40 text-primary">
        <Loader2 className="size-3.5 animate-spin" />
        Running
      </Badge>
    )
  return (
    <Badge variant="outline" className="gap-1.5 text-muted-foreground">
      Waiting
    </Badge>
  )
}

export function ProgressView({
  operationId,
  onDone,
}: {
  operationId: string
  onDone?: (status: string) => void
}) {
  const [logsOpen, setLogsOpen] = useState(true)
  const logRef = useRef<HTMLDivElement>(null)
  const notifiedRef = useRef(false)

  const { data: operation } = useQuery({
    queryKey: ["operation", operationId],
    queryFn: () => api.getOperation(operationId),
    refetchInterval: (query) => (query.state.data && TERMINAL.has(query.state.data.status) ? false : 1000),
  })

  const isTerminal = operation ? TERMINAL.has(operation.status) : false

  const { data: logs } = useQuery({
    queryKey: ["operation-logs", operationId],
    queryFn: () => api.getOperationLogs(operationId),
    refetchInterval: isTerminal ? false : 1000,
  })

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight })
  }, [logs])

  useEffect(() => {
    if (operation && isTerminal && !notifiedRef.current) {
      notifiedRef.current = true
      onDone?.(operation.status)
    }
  }, [operation, isTerminal, onDone])

  if (!operation) {
    return <Card className="p-6 text-sm text-muted-foreground">Loading operation…</Card>
  }

  return (
    <div className="space-y-4">
      <Card className="flex items-center justify-between p-5">
        <div>
          <div className="text-sm text-muted-foreground">{operation.operation_type}</div>
          <div className="text-lg font-semibold">{operation.stage ?? "Preparing"}</div>
        </div>
        {statusBadge(operation.status)}
      </Card>

      {operation.status === "FAILED" && operation.error && <ErrorPresentation error={operation.error} />}

      <Card className="p-0">
        <Collapsible open={logsOpen} onOpenChange={setLogsOpen}>
          <CollapsibleTrigger className="flex w-full items-center gap-1.5 border-b border-border px-4 py-3 text-sm font-medium">
            {logsOpen ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
            Live Log
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div ref={logRef} className="max-h-64 overflow-y-auto p-4 font-mono text-xs text-muted-foreground">
              {(logs?.logs ?? []).length === 0 && <div>Waiting for output…</div>}
              {(logs?.logs ?? []).map((entry) => (
                <div key={entry.sequence} className="py-0.5">
                  <span className="text-muted-foreground/60">{new Date(entry.occurred_at).toLocaleTimeString()}</span>{" "}
                  {entry.message}
                </div>
              ))}
            </div>
          </CollapsibleContent>
        </Collapsible>
      </Card>
    </div>
  )
}

import { useState } from "react"
import { AlertTriangle, ChevronDown, ChevronRight, RotateCw } from "lucide-react"
import type { PlatformErrorBody } from "@/types/api"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"

// Never show a raw exception (UX architecture §"Error Presentation") —
// every real PlatformError already carries a human `message`; this
// derives the surrounding Title/Possible Cause/Suggested Action from
// its `category`/`retryable` fields rather than a fixed lookup table
// for all ~70 catalog codes, since the category already communicates
// the right register of explanation.
const CATEGORY_TITLES: Record<string, string> = {
  INPUT: "Invalid input",
  CONFIG: "Configuration problem",
  STORAGE: "Release storage problem",
  IMPORT: "Import failed",
  CONTRACT: "Unsupported Release Contract",
  INTEGRITY: "Integrity check failed",
  COMPATIBILITY: "Incompatible Release",
  APPLICATION: "Application state problem",
  RELEASE: "Release problem",
  TRANSITION: "Action not available",
  OPERATION: "Operation problem",
  LOCK: "Application is busy",
  INSTALL: "Installation problem",
  UPDATE: "Update problem",
  VERIFY: "Verification problem",
  DOCKER: "Docker problem",
  SCRIPT: "Script execution problem",
  DATABASE: "Database problem",
  BACKUP: "Backup problem",
  RECOVERY: "Recovery problem",
  HOST: "Host state problem",
  FILESYSTEM: "Filesystem problem",
  INTERNAL: "Unexpected error",
}

function possibleCause(error: PlatformErrorBody): string {
  if (error.category === "LOCK") return "Another operation is already running for this application."
  if (error.category === "TRANSITION") return "The application is not currently in a state that allows this action."
  if (error.retryable) return "This is often a transient condition on the host or Docker Engine."
  return "This usually reflects a real, structural problem with the Release or the current configuration."
}

function suggestedAction(error: PlatformErrorBody): string {
  if (error.category === "LOCK") return "Wait for the current operation to finish, then try again."
  if (error.retryable) return "You can safely try this action again."
  return "Review the details below, or check the Release's own documentation, before retrying."
}

export function ErrorPresentation({
  error,
  onRetry,
}: {
  error: PlatformErrorBody
  onRetry?: () => void
}) {
  const [detailsOpen, setDetailsOpen] = useState(false)
  const title = CATEGORY_TITLES[error.category] ?? "Something went wrong"

  return (
    <Alert variant="destructive" className="border-destructive/40 bg-destructive/5">
      <AlertTriangle className="size-4" />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription className="flex flex-col gap-3">
        <p className="text-foreground">{error.message}</p>

        <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-sm">
          <dt className="text-muted-foreground">Possible cause</dt>
          <dd>{possibleCause(error)}</dd>
          <dt className="text-muted-foreground">Suggested action</dt>
          <dd>{suggestedAction(error)}</dd>
        </dl>

        {onRetry && error.retryable && (
          <Button size="sm" variant="outline" onClick={onRetry} className="w-fit gap-1.5">
            <RotateCw className="size-3.5" />
            Try again
          </Button>
        )}

        <Collapsible open={detailsOpen} onOpenChange={setDetailsOpen}>
          <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
            {detailsOpen ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
            Technical details
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2 space-y-1 rounded-md bg-muted/50 p-3 font-mono text-xs text-muted-foreground">
            <div>code: {error.code}</div>
            <div>category: {error.category}</div>
            {error.stage && <div>stage: {error.stage}</div>}
            {error.operation_id && <div>operation_id: {error.operation_id}</div>}
            {error.request_id && <div>request_id: {error.request_id}</div>}
            {Object.keys(error.details).length > 0 && (
              <pre className="whitespace-pre-wrap break-all">{JSON.stringify(error.details, null, 2)}</pre>
            )}
          </CollapsibleContent>
        </Collapsible>
      </AlertDescription>
    </Alert>
  )
}

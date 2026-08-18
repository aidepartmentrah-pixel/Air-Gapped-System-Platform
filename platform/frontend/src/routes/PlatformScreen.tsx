import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ScanLine, Download, CheckCircle2, AlertCircle } from "lucide-react"
import { api, PlatformApiError } from "@/lib/api"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ErrorPresentation } from "@/components/operations/ErrorPresentation"
import type { PlatformErrorBody } from "@/types/api"

export function PlatformScreen() {
  const queryClient = useQueryClient()
  const [error, setError] = useState<PlatformErrorBody | null>(null)

  const { data: candidates, isLoading } = useQuery({
    queryKey: ["release-candidates"],
    queryFn: api.listReleaseCandidates,
  })

  const scan = useMutation({
    mutationFn: api.scanReleaseCandidates,
    onSuccess: () => {
      setError(null)
      queryClient.invalidateQueries({ queryKey: ["release-candidates"] })
    },
    onError: (err) => setError(err instanceof PlatformApiError ? err.body : null),
  })

  const importCandidate = useMutation({
    mutationFn: (candidateId: string) => api.importReleaseCandidate(candidateId, "operator:ui"),
    onSuccess: () => {
      setError(null)
      queryClient.invalidateQueries({ queryKey: ["release-candidates"] })
      queryClient.invalidateQueries({ queryKey: ["applications"] })
    },
    onError: (err) => setError(err instanceof PlatformApiError ? err.body : null),
  })

  const items = candidates?.items ?? []

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Platform</h1>
          <p className="text-sm text-muted-foreground">Discover and import Releases from Release Storage.</p>
        </div>
        <Button onClick={() => scan.mutate()} disabled={scan.isPending} className="gap-1.5">
          <ScanLine className="size-4" />
          {scan.isPending ? "Scanning…" : "Scan for Releases"}
        </Button>
      </div>

      {error && <ErrorPresentation error={error} />}

      <Card className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Directory</TableHead>
              <TableHead>Application</TableHead>
              <TableHead>Version</TableHead>
              <TableHead>State</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  Loading…
                </TableCell>
              </TableRow>
            )}
            {!isLoading && items.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  No candidates found. Scan to discover Releases in storage.
                </TableCell>
              </TableRow>
            )}
            {items.map((candidate) => (
              <TableRow key={candidate.candidate_id}>
                <TableCell className="font-mono text-xs">{candidate.directory_name}</TableCell>
                <TableCell>{candidate.application_slug ?? "—"}</TableCell>
                <TableCell>{candidate.release_version ?? "—"}</TableCell>
                <TableCell>
                  {candidate.already_imported ? (
                    <Badge variant="outline" className="gap-1.5 border-success/40 text-success">
                      <CheckCircle2 className="size-3.5" />
                      Imported
                    </Badge>
                  ) : candidate.discovery_state === "READY_FOR_IMPORT" ? (
                    <Badge variant="outline" className="gap-1.5 text-muted-foreground">
                      Ready for import
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="gap-1.5 border-destructive/40 text-destructive">
                      <AlertCircle className="size-3.5" />
                      {candidate.discovery_state}
                    </Badge>
                  )}
                </TableCell>
                <TableCell className="text-right">
                  {!candidate.already_imported && candidate.discovery_state === "READY_FOR_IMPORT" && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="gap-1.5"
                      disabled={importCandidate.isPending}
                      onClick={() => importCandidate.mutate(candidate.candidate_id)}
                    >
                      <Download className="size-3.5" />
                      Import
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  )
}

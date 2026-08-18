import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { api } from "@/lib/api"
import type { Application } from "@/types/api"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

const STATE_LABEL: Record<string, string> = {
  ACTIVE: "Active",
  PREVIOUSLY_DEPLOYED: "Previously Deployed",
  NEVER_DEPLOYED: "Never Deployed",
  REMOVED_FROM_STORAGE: "Removed From Storage",
}

export function ReleasesTab({ application }: { application: Application }) {
  const { data } = useQuery({
    queryKey: ["application-releases", application.id],
    queryFn: () => api.listApplicationReleases(application.id),
  })
  const items = [...(data?.items ?? [])].reverse()

  return (
    <Card className="p-0">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Version</TableHead>
            <TableHead>Release Date</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.length === 0 && (
            <TableRow>
              <TableCell colSpan={4} className="text-center text-muted-foreground">
                No Releases imported yet.
              </TableCell>
            </TableRow>
          )}
          {items.map((release) => (
            <TableRow key={release.id}>
              <TableCell className="font-medium">{release.version}</TableCell>
              <TableCell className="text-muted-foreground">
                {release.created_at_engineering ? new Date(release.created_at_engineering).toLocaleDateString() : "—"}
              </TableCell>
              <TableCell>
                <Badge
                  variant="outline"
                  className={release.deployment_state === "ACTIVE" ? "border-success/40 text-success" : "text-muted-foreground"}
                >
                  {STATE_LABEL[release.deployment_state] ?? release.deployment_state}
                </Badge>
              </TableCell>
              <TableCell className="text-right">
                {release.deployment_state !== "ACTIVE" && !application.active_deployment && release.supported_operations.fresh_install && (
                  <Button asChild size="sm" variant="outline">
                    <Link to="/applications/$applicationId/install" params={{ applicationId: application.id }} search={{ releaseId: release.id }}>
                      Install
                    </Link>
                  </Button>
                )}
                {release.deployment_state !== "ACTIVE" && application.active_deployment && release.supported_operations.update && (
                  <Button asChild size="sm" variant="outline">
                    <Link to="/applications/$applicationId/update" params={{ applicationId: application.id }} search={{ releaseId: release.id }}>
                      Details
                    </Link>
                  </Button>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  )
}

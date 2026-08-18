import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { ArrowUpCircle, PackageOpen } from "lucide-react"
import { api } from "@/lib/api"
import type { Application } from "@/types/api"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"

export function ApplicationCard({ application }: { application: Application }) {
  const { data: releases } = useQuery({
    queryKey: ["application-releases", application.id],
    queryFn: () => api.listApplicationReleases(application.id),
  })

  const latest = releases?.items.at(-1)
  const installed = application.active_deployment
  const updateAvailable =
    installed && latest && latest.version !== installed.version && latest.supported_operations.update

  return (
    <Card className="flex flex-col gap-3 p-5">
      <div>
        <h3 className="text-base font-semibold">{application.name}</h3>
        {application.description && (
          <p className="mt-0.5 text-sm text-muted-foreground">{application.description}</p>
        )}
      </div>

      {installed ? (
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <div className="text-xs text-muted-foreground">Installed Version</div>
            <div className="font-medium">{installed.version}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">Latest Version</div>
            <div className="font-medium">{latest?.version ?? "—"}</div>
          </div>
        </div>
      ) : (
        <div className="text-sm">
          <div className="text-xs text-muted-foreground">Latest Version</div>
          <div className="font-medium">{latest?.version ?? "—"}</div>
        </div>
      )}

      <div>
        {!installed && (
          <Badge variant="outline" className="gap-1.5 text-muted-foreground">
            <PackageOpen className="size-3.5" />
            Not Installed
          </Badge>
        )}
        {installed && updateAvailable && (
          <Badge variant="outline" className="gap-1.5 border-warning/40 text-warning">
            <ArrowUpCircle className="size-3.5" />
            Update Available
          </Badge>
        )}
        {installed && !updateAvailable && (
          <Badge variant="outline" className="gap-1.5 border-success/40 text-success">
            Up to date
          </Badge>
        )}
      </div>

      <div className="mt-1 flex gap-2">
        {!installed && latest && (
          <Button asChild size="sm">
            <Link to="/applications/$applicationId/install" params={{ applicationId: application.id }} search={{ releaseId: latest.id }}>
              Install
            </Link>
          </Button>
        )}
        {installed && updateAvailable && latest && (
          <Button asChild size="sm">
            <Link to="/applications/$applicationId/update" params={{ applicationId: application.id }} search={{ releaseId: latest.id }}>
              Update
            </Link>
          </Button>
        )}
        <Button asChild size="sm" variant="outline">
          <Link to="/applications/$applicationId" params={{ applicationId: application.id }}>
            Open
          </Link>
        </Button>
      </div>
    </Card>
  )
}

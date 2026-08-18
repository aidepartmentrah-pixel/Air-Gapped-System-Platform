import { useQueries, useQuery } from "@tanstack/react-query"
import { Boxes, ArrowUpCircle, Loader2, HeartPulse } from "lucide-react"
import { api } from "@/lib/api"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { ApplicationCard } from "@/components/applications/ApplicationCard"

function StatCard({
  label,
  value,
  icon: Icon,
}: {
  label: string
  value: React.ReactNode
  icon: React.ComponentType<{ className?: string }>
}) {
  return (
    <Card className="flex flex-row items-center gap-4 p-5">
      <div className="flex size-10 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
        <Icon className="size-5" />
      </div>
      <div>
        <div className="text-2xl font-semibold">{value}</div>
        <div className="text-xs text-muted-foreground">{label}</div>
      </div>
    </Card>
  )
}

export function Dashboard() {
  const { data: applications, isLoading: applicationsLoading } = useQuery({
    queryKey: ["applications"],
    queryFn: api.listApplications,
  })
  const { data: runningOps } = useQuery({
    queryKey: ["operations", "RUNNING"],
    queryFn: () => api.listOperations("RUNNING"),
    refetchInterval: 5_000,
  })
  const { data: recentOps } = useQuery({
    queryKey: ["operations", "recent"],
    queryFn: () => api.listOperations(undefined, 8),
    refetchInterval: 10_000,
  })
  const { data: health } = useQuery({ queryKey: ["health"], queryFn: api.health })

  const items = applications?.items ?? []
  const installedCount = items.filter((a) => a.active_deployment).length

  const releaseQueries = useQueries({
    queries: items.map((app) => ({
      queryKey: ["application-releases", app.id],
      queryFn: () => api.listApplicationReleases(app.id),
      enabled: items.length > 0,
    })),
  })
  const updatesAvailable = items.reduce((count, app, index) => {
    if (!app.active_deployment) return count
    const latest = releaseQueries[index]?.data?.items.at(-1)
    const hasUpdate = latest && latest.version !== app.active_deployment.version && latest.supported_operations.update
    return hasUpdate ? count + 1 : count
  }, 0)

  return (
    <div className="flex gap-6">
      <div className="min-w-0 flex-1 space-y-6">
        <div>
          <h1 className="text-2xl font-semibold">Dashboard</h1>
          <p className="text-sm text-muted-foreground">What is the current state of my platform?</p>
        </div>

        <div className="grid grid-cols-4 gap-4">
          <StatCard label="Applications Installed" value={installedCount} icon={Boxes} />
          <StatCard label="Updates Available" value={updatesAvailable} icon={ArrowUpCircle} />
          <StatCard label="Running Operations" value={runningOps?.items.length ?? 0} icon={Loader2} />
          <StatCard
            label="System Health"
            value={health?.status === "READY" ? "Healthy" : "Degraded"}
            icon={HeartPulse}
          />
        </div>

        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Applications</h2>
          {applicationsLoading ? (
            <div className="grid grid-cols-2 gap-4 xl:grid-cols-3">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-40 rounded-lg" />
              ))}
            </div>
          ) : items.length === 0 ? (
            <Card className="p-8 text-center text-sm text-muted-foreground">
              No applications yet. Import a Release from the Platform screen to get started.
            </Card>
          ) : (
            <div className="grid grid-cols-2 gap-4 xl:grid-cols-3">
              {items.map((app) => (
                <ApplicationCard key={app.id} application={app} />
              ))}
            </div>
          )}
        </div>
      </div>

      <aside className="w-72 shrink-0 space-y-4">
        <Card className="p-4">
          <h3 className="mb-3 text-sm font-semibold">Platform Status</h3>
          <div className="space-y-2 text-sm">
            {health &&
              Object.entries(health.checks).map(([check, status]) => (
                <div key={check} className="flex items-center justify-between">
                  <span className="capitalize text-muted-foreground">{check}</span>
                  <Badge
                    variant="outline"
                    className={status === "PASS" ? "border-success/40 text-success" : "border-destructive/40 text-destructive"}
                  >
                    {status}
                  </Badge>
                </div>
              ))}
          </div>
        </Card>

        <Card className="p-4">
          <h3 className="mb-3 text-sm font-semibold">Recent Activity</h3>
          {!recentOps || recentOps.items.length === 0 ? (
            <p className="text-sm text-muted-foreground">No recent operations.</p>
          ) : (
            <ul className="space-y-2.5 text-sm">
              {recentOps.items.map((op) => (
                <li key={op.operation_id} className="flex items-center justify-between gap-2">
                  <span className="truncate text-muted-foreground">{op.operation_type}</span>
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
      </aside>
    </div>
  )
}

import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { OverviewTab } from "@/components/applications/OverviewTab"
import { ReleasesTab } from "@/components/applications/ReleasesTab"
import { HistoryTab } from "@/components/applications/HistoryTab"
import { SettingsTab } from "@/components/applications/SettingsTab"

export function ApplicationDetails({ applicationId }: { applicationId: string }) {
  const { data: application, isLoading } = useQuery({
    queryKey: ["application", applicationId],
    queryFn: () => api.getApplication(applicationId),
  })

  if (isLoading || !application) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold">{application.name}</h1>
          {application.active_deployment && (
            <span className="text-sm text-muted-foreground">v{application.active_deployment.version}</span>
          )}
          <Badge
            variant="outline"
            className={
              application.operational_health === "HEALTHY"
                ? "border-success/40 text-success"
                : application.operational_health === "UNHEALTHY"
                  ? "border-destructive/40 text-destructive"
                  : "text-muted-foreground"
            }
          >
            {application.operational_health.replace("_", " ")}
          </Badge>
        </div>
      </div>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="releases">Releases</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
        </TabsList>
        <TabsContent value="overview" className="mt-4">
          <OverviewTab application={application} />
        </TabsContent>
        <TabsContent value="releases" className="mt-4">
          <ReleasesTab application={application} />
        </TabsContent>
        <TabsContent value="history" className="mt-4">
          <HistoryTab application={application} />
        </TabsContent>
        <TabsContent value="settings" className="mt-4">
          <SettingsTab application={application} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

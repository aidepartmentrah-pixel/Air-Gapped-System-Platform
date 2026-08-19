import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { ApplicationCard } from "@/components/applications/ApplicationCard"

export function ApplicationsList() {
  const { data, isLoading } = useQuery({ queryKey: ["applications"], queryFn: api.listApplications })
  const items = data?.items ?? []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Applications</h1>
        <p className="text-sm text-muted-foreground">Every application known to this Platform.</p>
      </div>

      {isLoading ? (
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
  )
}

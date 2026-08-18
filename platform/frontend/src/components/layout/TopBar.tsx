import { useQuery } from "@tanstack/react-query"
import { CircleCheck, CircleAlert, User } from "lucide-react"
import { api } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

export function TopBar() {
  const { data } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 15_000,
  })
  const isReady = data?.status === "READY"

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border px-6">
      <div className="flex items-center gap-2">
        <div className="flex size-7 items-center justify-center rounded-md bg-primary text-sm font-semibold text-primary-foreground">
          R
        </div>
        <span className="text-sm font-semibold">RAH</span>
        <span className="text-sm text-muted-foreground">Offline Installation Platform</span>
      </div>

      <div className="flex items-center gap-4">
        <Badge
          variant="outline"
          className={
            isReady
              ? "gap-1.5 border-success/40 text-success"
              : "gap-1.5 border-warning/40 text-warning"
          }
        >
          {isReady ? <CircleCheck className="size-3.5" /> : <CircleAlert className="size-3.5" />}
          {isReady ? "Platform Ready" : "Platform Degraded"}
        </Badge>

        <DropdownMenu>
          <DropdownMenuTrigger className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-foreground">
            <User className="size-4" strokeWidth={1.75} />
            Operator
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem disabled>operator:unknown</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}

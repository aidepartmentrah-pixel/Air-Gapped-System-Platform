import { Link, useRouterState } from "@tanstack/react-router"
import { LayoutDashboard, Boxes, Server, Settings } from "lucide-react"
import { cn } from "@/lib/utils"

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/applications", label: "Applications", icon: Boxes },
  { to: "/platform", label: "Platform", icon: Server },
  { to: "/settings", label: "Settings", icon: Settings },
] as const

export function Sidebar() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })

  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-sidebar-border bg-sidebar">
      <nav className="flex flex-col gap-1 p-3">
        {NAV_ITEMS.map((item) => {
          const isActive =
            item.to === "/" ? pathname === "/" : pathname.startsWith(item.to)
          const Icon = item.icon
          return (
            <Link
              key={item.to}
              to={item.to}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-sidebar-accent text-sidebar-foreground"
                  : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-foreground"
              )}
            >
              <Icon className="size-4" strokeWidth={1.75} />
              {item.label}
            </Link>
          )
        })}
      </nav>
    </aside>
  )
}

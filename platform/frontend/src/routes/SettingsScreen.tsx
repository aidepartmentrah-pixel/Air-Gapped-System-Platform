import { Card } from "@/components/ui/card"

export function SettingsScreen() {
  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-muted-foreground">Platform-level settings.</p>
      </div>
      <Card className="p-8 text-center text-sm text-muted-foreground">
        Platform-level settings are not yet implemented in Period A. Per-application configuration
        lives on each application's own Settings tab.
      </Card>
    </div>
  )
}

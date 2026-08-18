import { createRootRoute, createRoute, createRouter } from "@tanstack/react-router"
import { z } from "zod"
import { AppLayout } from "@/components/layout/AppLayout"
import { Dashboard } from "@/routes/Dashboard"
import { ApplicationsList } from "@/routes/ApplicationsList"
import { ApplicationDetails } from "@/routes/ApplicationDetails"
import { InstallWizard } from "@/routes/InstallWizard"
import { UpdateFlow } from "@/routes/UpdateFlow"
import { PlatformScreen } from "@/routes/PlatformScreen"
import { SettingsScreen } from "@/routes/SettingsScreen"

const rootRoute = createRootRoute({
  component: AppLayout,
})

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: Dashboard,
})

const applicationsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/applications",
  component: ApplicationsList,
})

const applicationDetailsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/applications/$applicationId",
  component: () => {
    const { applicationId } = applicationDetailsRoute.useParams()
    return <ApplicationDetails applicationId={applicationId} />
  },
})

const releaseSearchSchema = z.object({ releaseId: z.string() })

const installRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/applications/$applicationId/install",
  validateSearch: releaseSearchSchema,
  component: () => {
    const { applicationId } = installRoute.useParams()
    const { releaseId } = installRoute.useSearch()
    return <InstallWizard applicationId={applicationId} releaseId={releaseId} />
  },
})

const updateRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/applications/$applicationId/update",
  validateSearch: releaseSearchSchema,
  component: () => {
    const { applicationId } = updateRoute.useParams()
    const { releaseId } = updateRoute.useSearch()
    return <UpdateFlow applicationId={applicationId} releaseId={releaseId} />
  },
})

const platformRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/platform",
  component: PlatformScreen,
})

const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings",
  component: SettingsScreen,
})

const routeTree = rootRoute.addChildren([
  indexRoute,
  applicationsRoute,
  applicationDetailsRoute,
  installRoute,
  updateRoute,
  platformRoute,
  settingsRoute,
])

export const router = createRouter({ routeTree })

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}

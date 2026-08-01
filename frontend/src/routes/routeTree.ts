import { createRootRoute, createRoute } from "@tanstack/react-router";
import React from "react";
import { RootLayout } from "./root";
import { DashboardPage } from "./dashboard";
import { NewHuntPage } from "./new-hunt";
import { DeepSearchPage } from "./deep-search";
import { HuntDetailPage } from "./hunt-detail";
import { AutomationJobPage } from "./automation-job";
import { SettingsPage } from "./settings";
import { FoundationPage } from "./foundation";
import { ModulePlaceholderPage } from "./module-placeholder";
import { IntegrationCenterPage } from "./integration-center";
import { LeadPoolPage } from "./lead-pool";

const rootRoute = createRootRoute({ component: RootLayout });

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: DashboardPage,
});

const newHuntRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/hunts/new",
  component: NewHuntPage,
});

const deepSearchRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/deep-search",
  component: DeepSearchPage,
});

const huntDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/hunts/$huntId",
  component: HuntDetailPage,
});

const automationJobRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/automation/$jobId",
  component: AutomationJobPage,
});

const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings",
  component: SettingsPage,
});

const foundationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/foundation",
  component: FoundationPage,
});

const leadsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/leads",
  component: LeadPoolPage,
});

const productsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/products",
  component: () => React.createElement(ModulePlaceholderPage, { module: "products" }),
});

const matchesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/matches",
  component: () => React.createElement(ModulePlaceholderPage, { module: "matches" }),
});

const quotesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/quotes",
  component: () => React.createElement(ModulePlaceholderPage, { module: "quotes" }),
});

const knowledgeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/knowledge",
  component: () => React.createElement(ModulePlaceholderPage, { module: "knowledge" }),
});

const integrationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/integration-center",
  component: IntegrationCenterPage,
});

export const routeTree = rootRoute.addChildren([
  indexRoute,
  newHuntRoute,
  deepSearchRoute,
  huntDetailRoute,
  automationJobRoute,
  foundationRoute,
  leadsRoute,
  productsRoute,
  matchesRoute,
  quotesRoute,
  knowledgeRoute,
  integrationRoute,
  settingsRoute,
]);

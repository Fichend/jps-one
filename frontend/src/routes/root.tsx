import { useQuery } from "@tanstack/react-query";
import { Link, Outlet } from "@tanstack/react-router";
import {
  Boxes,
  Crosshair,
  Database,
  FileText,
  LayoutDashboard,
  Layers3,
  Mail,
  PackageCheck,
  Plus,
  Search,
  Settings,
  Users,
} from "lucide-react";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const mainNav = [
  { to: "/", label: "任务看板", icon: LayoutDashboard },
  { to: "/hunts/new", label: "新建任务", icon: Plus },
  { to: "/deep-search", label: "深度搜索", icon: Search },
  { to: "/integration-center", label: "邮件发送", icon: Mail },
  { to: "/leads", label: "客户池", icon: Users },
  { to: "/products", label: "产品库", icon: Boxes },
  { to: "/matches", label: "匹配中心", icon: PackageCheck },
  { to: "/quotes", label: "报价中心", icon: FileText },
  { to: "/knowledge", label: "知识库", icon: Database },
  { to: "/foundation", label: "配置中心", icon: Layers3, adminOnly: true },
] as const;

export function RootLayout() {
  const { data: currentUser } = useQuery({
    queryKey: ["current-user"],
    queryFn: api.getCurrentUser,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
  const isAdmin = currentUser?.username === "jpsadmin";
  const visibleNav = mainNav.filter((item) => !("adminOnly" in item) || isAdmin);

  return (
    <div className="min-h-screen bg-[#f6f8fb] text-foreground">
      <div className="flex min-h-screen">
        <aside className="hidden w-64 shrink-0 border-r bg-white lg:flex lg:flex-col">
          <div className="flex h-16 items-center gap-3 border-b px-5">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <Crosshair className="h-5 w-5" />
            </div>
            <div>
              <div className="text-lg font-semibold leading-none">JPS One</div>
              <div className="mt-1 text-xs text-muted-foreground">jps-one.com</div>
            </div>
          </div>
          <nav className="flex-1 space-y-1 px-3 py-4">
            {visibleNav.map((item) => {
              const Icon = item.icon;
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={cn(
                    "flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium text-muted-foreground transition-colors",
                    "hover:bg-accent hover:text-foreground [&.active]:bg-primary/10 [&.active]:text-primary"
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="border-t p-3">
            {isAdmin ? (
              <Link
                to="/settings"
                className="flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground [&.active]:bg-primary/10 [&.active]:text-primary"
              >
                <Settings className="h-4 w-4" />
                系统设置
              </Link>
            ) : (
              <div className="rounded-md border bg-[#fbfcfe] px-3 py-2 text-xs text-muted-foreground">
                当前账号：{currentUser?.username || "访客"}
              </div>
            )}
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-40 border-b bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/80">
            <div className="flex min-h-16 flex-col gap-3 px-4 py-3 lg:flex-row lg:items-center lg:justify-between lg:px-6 lg:py-0">
              <div className="flex items-center justify-between gap-3 lg:hidden">
                <Link to="/" className="flex items-center gap-2 text-lg font-semibold">
                  <Crosshair className="h-5 w-5 text-primary" />
                  <span>JPS One</span>
                </Link>
                <Link to="/hunts/new">
                  <Button size="sm">
                    <Plus className="mr-2 h-4 w-4" />
                    新建
                  </Button>
                </Link>
              </div>
              <nav className="flex min-w-0 gap-2 overflow-x-auto pb-1 lg:hidden">
                {visibleNav.map((item) => {
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.to}
                      to={item.to}
                      className="flex shrink-0 items-center gap-1.5 rounded-md border bg-white px-3 py-2 text-xs font-medium text-muted-foreground [&.active]:border-primary/30 [&.active]:bg-primary/10 [&.active]:text-primary"
                    >
                      <Icon className="h-3.5 w-3.5" />
                      {item.label}
                    </Link>
                  );
                })}
              </nav>
              <div className="hidden lg:block">
                <div className="text-sm font-medium">JPS 医疗外贸智能运营系统</div>
                <div className="mt-1 text-xs text-muted-foreground">获客 · 匹配 · 报价 · 跟进 · 知识库</div>
              </div>
              <div className="hidden items-center gap-2 lg:flex">
                {isAdmin ? (
                  <Link to="/settings">
                    <Button variant="outline" size="sm">
                      <Settings className="mr-2 h-4 w-4" />
                      设置
                    </Button>
                  </Link>
                ) : null}
                <Link to="/hunts/new">
                  <Button size="sm">
                    <Plus className="mr-2 h-4 w-4" />
                    新建任务
                  </Button>
                </Link>
              </div>
            </div>
          </header>
          <main className="min-w-0 flex-1 px-4 py-6 lg:px-6">
            <div className="mx-auto w-full max-w-7xl">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}

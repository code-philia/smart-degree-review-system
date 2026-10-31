import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import {
  ChevronDown,
  ClipboardList,
  History,
  LogIn,
  LogOut,
  ShieldCheck,
  Sparkles,
  type LucideIcon,
} from 'lucide-react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuthSession } from '../auth/AuthSessionProvider';
import { Avatar, AvatarFallback } from '../components/shadcn/avatar';
import { Badge } from '../components/shadcn/badge';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '../components/shadcn/breadcrumb';
import { SystemFeedbackDialog } from '../components/SystemFeedbackDialog';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '../components/shadcn/collapsible';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../components/shadcn/dropdown-menu';
import { Separator } from '../components/shadcn/separator';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarSeparator,
  SidebarTrigger,
  useSidebar,
} from '../components/shadcn/sidebar';
import { Skeleton } from '../components/shadcn/skeleton';
import {
  findNavItemLabel,
  getVisibleNavGroups,
  type NavGroup,
  type NavItem,
} from '../nav/navigationConfig';

const PRODUCT_NAME = '智慧学位 AI 评阅辅助系统';
const PRODUCT_TAGLINE = '试点验证版 V0.9';

const NAV_ICONS: Record<string, LucideIcon> = {
  '/thirty-rules-check': ClipboardList,
  '/thirty-rules-check/reports': History,
};

function isNavItemActive(pathname: string, item: NavItem) {
  if (pathname === item.to) {
    return true;
  }

  const prefix = item.matchPrefix ?? item.to;
  return (
    pathname.startsWith(`${prefix}/`) ||
    (item.relatedPrefixes || []).some(
      (relatedPrefix) => pathname === relatedPrefix || pathname.startsWith(`${relatedPrefix}/`),
    )
  );
}

function NavigationGroup({
  group,
  pathname,
  expanded,
  onExpandedChange,
}: {
  group: NavGroup;
  pathname: string;
  expanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
}) {
  const { setOpenMobile } = useSidebar();

  return (
    <Collapsible open={expanded} onOpenChange={onExpandedChange} className="group/collapsible">
      <SidebarGroup className="py-1">
        <SidebarGroupLabel asChild>
          <CollapsibleTrigger className="w-full cursor-pointer font-semibold uppercase tracking-wide">
            <span>{group.title}</span>
            <ChevronDown className="ml-auto transition-transform group-data-[state=open]/collapsible:rotate-180" />
          </CollapsibleTrigger>
        </SidebarGroupLabel>
        <CollapsibleContent>
          <SidebarGroupContent>
            <SidebarMenu>
              {group.items.map((item) => {
                const Icon = NAV_ICONS[item.to] ?? Sparkles;
                const isActive = isNavItemActive(pathname, item);

                return (
                  <SidebarMenuItem key={item.to}>
                    <SidebarMenuButton
                      asChild
                      isActive={isActive}
                      tooltip={item.label}
                      className="h-9 font-medium data-active:bg-sidebar-accent data-active:text-sidebar-accent-foreground"
                    >
                      <NavLink to={item.to} end onClick={() => setOpenMobile(false)}>
                        <Icon aria-hidden="true" />
                        <span>{item.label}</span>
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </CollapsibleContent>
      </SidebarGroup>
    </Collapsible>
  );
}

function AccountMenu({ onLogout }: { onLogout: () => Promise<void> }) {
  const { status, user } = useAuthSession();
  const { setOpenMobile } = useSidebar();
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  async function handleLogout() {
    setIsLoggingOut(true);
    try {
      await onLogout();
      setOpenMobile(false);
    } finally {
      setIsLoggingOut(false);
    }
  }

  if (status === 'loading') {
    return (
      <div className="flex h-12 items-center gap-2 px-2">
        <Skeleton className="size-8 rounded-full bg-sidebar-accent" />
        <div className="min-w-0 flex-1 space-y-1.5 group-data-[collapsible=icon]:hidden">
          <Skeleton className="h-3 w-24 bg-sidebar-accent" />
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton asChild tooltip="登录系统" className="h-9 bg-sidebar-accent font-medium">
            <Link to="/auth" onClick={() => setOpenMobile(false)}>
              <LogIn aria-hidden="true" />
              <span>登录系统</span>
            </Link>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    );
  }

  const displayName = user.displayName?.trim() || user.username;
  const userInitial = Array.from(displayName)[0]?.toUpperCase() ?? '用';

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton size="lg" tooltip="账户菜单" className="data-open:bg-sidebar-accent">
              <Avatar className="size-8 border border-sidebar-border">
                <AvatarFallback className="bg-sidebar-primary font-semibold text-sidebar-primary-foreground">
                  {userInitial}
                </AvatarFallback>
              </Avatar>
              <div className="min-w-0 flex-1 text-left leading-tight">
                <span className="block truncate font-semibold">{displayName}</span>
              </div>
              <ChevronDown className="ml-auto" aria-hidden="true" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="right" align="end" sideOffset={8} className="w-64">
            <DropdownMenuLabel className="space-y-1 px-2 py-2">
              <span className="block truncate text-sm font-semibold text-popover-foreground">{displayName}</span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              variant="destructive"
              disabled={isLoggingOut}
              onSelect={() => void handleLogout()}
              className="py-2"
            >
              <LogOut aria-hidden="true" />
              {isLoggingOut ? '正在退出…' : '退出登录'}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}

function AppShell() {
  const { user, logout } = useAuthSession();
  const location = useLocation();
  const navigate = useNavigate();
  const role = user?.role ?? null;
  const visibleGroups = useMemo(() => getVisibleNavGroups(role), [role]);
  const currentNavInfo = useMemo(() => findNavItemLabel(location.pathname), [location.pathname]);
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(() => new Set(visibleGroups.map((group) => group.key)));

  useEffect(() => {
    const activeGroup = visibleGroups.find((group) =>
      group.items.some((item) => isNavItemActive(location.pathname, item)),
    );

    if (!activeGroup) {
      return;
    }

    setExpandedKeys((current) => {
      if (current.has(activeGroup.key)) {
        return current;
      }

      const next = new Set(current);
      next.add(activeGroup.key);
      return next;
    });
  }, [location.pathname, visibleGroups]);

  function setGroupExpanded(key: string, expanded: boolean) {
    setExpandedKeys((current) => {
      const next = new Set(current);
      if (expanded) {
        next.add(key);
      } else {
        next.delete(key);
      }
      return next;
    });
  }

  async function handleLogout() {
    await logout();
    navigate('/auth');
  }

  const pageTitle = currentNavInfo?.label || '当前页面';

  return (
    <SidebarProvider
      className="academic-shell"
      style={
        {
          '--sidebar-width': '15.25rem',
          '--sidebar-width-icon': '3.25rem',
        } as CSSProperties
      }
    >
      <Sidebar collapsible="icon" aria-label="主导航">
        <SidebarHeader className="p-2.5">
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton size="lg" tooltip={PRODUCT_NAME} className="h-14 hover:bg-sidebar-accent/70">
                <img
                  src="/brand-mark.jpg"
                  alt=""
                  className="size-7 rounded-full object-cover ring-1 ring-sidebar-border"
                />
                <span className="min-w-0 leading-tight">
                  <span className="block whitespace-normal text-xs font-semibold leading-5">{PRODUCT_NAME}</span>
                  <span className="block text-[10px] font-normal text-sidebar-foreground/60">{PRODUCT_TAGLINE}</span>
                </span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarHeader>

        <SidebarSeparator />

        <SidebarContent aria-label="主导航菜单">
          {visibleGroups.map((group) => (
            <NavigationGroup
              key={group.key}
              group={group}
              pathname={location.pathname}
              expanded={expandedKeys.has(group.key)}
              onExpandedChange={(expanded) => setGroupExpanded(group.key, expanded)}
            />
          ))}
        </SidebarContent>

        <SidebarSeparator />
        <SidebarFooter className="p-2.5">
          <AccountMenu onLogout={handleLogout} />
        </SidebarFooter>
        <SidebarRail aria-label="收起或展开主导航" title="收起或展开主导航" />
      </Sidebar>

      <SidebarInset className="min-w-0 bg-background">
        <header className="app-topbar sticky top-0 z-20 flex h-14 shrink-0 items-center justify-between gap-4 border-b bg-background/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/80 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <SidebarTrigger aria-label="切换主导航" className="shrink-0" />
            <Separator orientation="vertical" className="h-5" />
            <Breadcrumb className="min-w-0">
              <BreadcrumbList className="flex-nowrap text-xs sm:text-sm">
                {currentNavInfo?.groupTitle ? (
                  <>
                    <BreadcrumbItem className="hidden sm:inline-flex">
                      <span>{currentNavInfo.groupTitle}</span>
                    </BreadcrumbItem>
                    <BreadcrumbSeparator className="hidden sm:list-item" />
                  </>
                ) : null}
                <BreadcrumbItem className="min-w-0">
                  <BreadcrumbPage className="truncate font-medium">{pageTitle}</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </div>

          <div className="flex items-center gap-2">
            <span className="hidden shrink-0 sm:inline-flex">
              <Badge variant="outline" className="border-primary/20 bg-primary/5 text-primary">
                <ShieldCheck aria-hidden="true" />
                试点验证版
              </Badge>
            </span>
            {user ? <SystemFeedbackDialog /> : null}
          </div>
        </header>

        <main className="app-content flex-1 px-4 py-5 sm:px-6 lg:px-7">
          <div className="mx-auto w-full max-w-7xl">
            <Outlet />
          </div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}

export default AppShell;

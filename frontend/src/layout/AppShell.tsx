import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import {
  Bot,
  BookOpenCheck,
  BrainCircuit,
  Calculator,
  ChartColumn,
  ChartNoAxesCombined,
  ChevronDown,
  CircleHelp,
  ClipboardList,
  Database,
  FileCheck2,
  Files,
  History,
  Home,
  Inbox,
  LibraryBig,
  Lightbulb,
  LogIn,
  LogOut,
  MessageSquareText,
  Search,
  Send,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  TextCursorInput,
  UserRoundSearch,
  WandSparkles,
  type LucideIcon,
} from 'lucide-react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuthSession } from '../auth/AuthSessionProvider';
import { Avatar, AvatarFallback } from '../components/shadcn/avatar';
import { Badge } from '../components/shadcn/badge';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '../components/shadcn/breadcrumb';
import { Button } from '../components/shadcn/button';
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
  roleLabels,
  roleScopeLabels,
  type NavGroup,
  type NavItem,
} from '../nav/navigationConfig';

const PRODUCT_NAME = '智慧学位 AI 评阅辅助系统';
const PRODUCT_TAGLINE = '试点验证版 V0.9';

const NAV_ICONS: Record<string, LucideIcon> = {
  '/normative-check': FileCheck2,
  '/normative-reports': History,
  '/duplication-detect': Search,
  '/duplication-history': Files,
  '/whole-polish': WandSparkles,
  '/local-polish': TextCursorInput,
  '/polish-history': ClipboardList,
  '/innovation-assessment': Lightbulb,
  '/innovation-scoring': Calculator,
  '/innovation-history': BrainCircuit,
  '/ai-review': Bot,
  '/ai-review/history': BookOpenCheck,
  '/ledger-records': Database,
  '/ledger-stats': ChartColumn,
  '/quality-dashboard': ChartNoAxesCombined,
  '/student-quality-portrait': UserRoundSearch,
  '/student-report-submissions': Send,
  '/student-report-results': MessageSquareText,
  '/supervisor-review-queue': Inbox,
  '/rule-config': SlidersHorizontal,
  '/duplication-corpus': LibraryBig,
  '/about': CircleHelp,
};

function isNavItemActive(pathname: string, item: NavItem) {
  if (pathname === item.to) {
    return true;
  }

  const prefix = item.matchPrefix ?? item.to;
  return pathname.startsWith(`${prefix}/`);
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
          <Skeleton className="h-2.5 w-16 bg-sidebar-accent" />
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

  const userInitial = Array.from(user.username)[0]?.toUpperCase() ?? '用';

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
                <span className="block truncate font-semibold">{user.username}</span>
                <span className="block truncate text-xs text-sidebar-foreground/65">{roleLabels[user.role]}</span>
              </div>
              <ChevronDown className="ml-auto" aria-hidden="true" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="right" align="end" sideOffset={8} className="w-64">
            <DropdownMenuLabel className="space-y-1 px-2 py-2">
              <span className="block text-sm font-semibold text-popover-foreground">{user.username}</span>
              <span className="block font-normal text-muted-foreground">
                {roleLabels[user.role]} · {roleScopeLabels[user.role]}
              </span>
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

  const pageTitle = location.pathname === '/' ? '工作台' : currentNavInfo?.label || '当前页面';

  return (
    <SidebarProvider
      style={
        {
          '--sidebar-width': '17.5rem',
          '--sidebar-width-icon': '3.5rem',
        } as CSSProperties
      }
    >
      <Sidebar collapsible="icon" aria-label="主导航">
        <SidebarHeader className="p-3">
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton asChild size="lg" tooltip={PRODUCT_NAME} className="h-12 hover:bg-sidebar-accent/70">
                <Link to="/">
                  <img
                    src="/brand-mark.jpg"
                    alt=""
                    className="size-8 rounded-full object-cover ring-1 ring-sidebar-border"
                  />
                  <span className="min-w-0 leading-tight">
                    <span className="block truncate font-semibold">{PRODUCT_NAME}</span>
                    <span className="mt-1 block text-xs font-normal text-sidebar-foreground/60">{PRODUCT_TAGLINE}</span>
                  </span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarHeader>

        <SidebarSeparator />

        <SidebarContent aria-label="主导航菜单">
          <SidebarGroup className="pb-1">
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton
                    asChild
                    isActive={location.pathname === '/'}
                    tooltip="工作台"
                    className="h-9 font-medium"
                  >
                    <NavLink to="/" end>
                      <Home aria-hidden="true" />
                      <span>工作台</span>
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>

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
        <SidebarFooter className="p-3">
          {user ? (
            <div className="mb-1 flex items-center gap-2 px-2 text-xs text-sidebar-foreground/60 group-data-[collapsible=icon]:hidden">
              <ShieldCheck className="size-3.5" aria-hidden="true" />
              <span>{roleScopeLabels[user.role]}</span>
            </div>
          ) : null}
          <AccountMenu onLogout={handleLogout} />
        </SidebarFooter>
        <SidebarRail aria-label="收起或展开主导航" title="收起或展开主导航" />
      </Sidebar>

      <SidebarInset className="min-w-0 bg-background">
        <header className="sticky top-0 z-20 flex h-16 shrink-0 items-center justify-between gap-4 border-b bg-background/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/80 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <SidebarTrigger aria-label="切换主导航" className="shrink-0" />
            <Separator orientation="vertical" className="h-5" />
            <Breadcrumb className="min-w-0">
              <BreadcrumbList className="flex-nowrap text-xs sm:text-sm">
                {location.pathname === '/' ? (
                  <BreadcrumbItem>
                    <BreadcrumbPage className="truncate font-medium">工作台</BreadcrumbPage>
                  </BreadcrumbItem>
                ) : (
                  <>
                    <BreadcrumbItem className="hidden sm:inline-flex">
                      <BreadcrumbLink asChild>
                        <Link to="/">工作台</Link>
                      </BreadcrumbLink>
                    </BreadcrumbItem>
                    <BreadcrumbSeparator className="hidden sm:list-item" />
                    {currentNavInfo?.groupTitle ? (
                      <>
                        <BreadcrumbItem className="hidden md:inline-flex">
                          <span>{currentNavInfo.groupTitle}</span>
                        </BreadcrumbItem>
                        <BreadcrumbSeparator className="hidden md:list-item" />
                      </>
                    ) : null}
                    <BreadcrumbItem className="min-w-0">
                      <BreadcrumbPage className="truncate font-medium">{pageTitle}</BreadcrumbPage>
                    </BreadcrumbItem>
                  </>
                )}
              </BreadcrumbList>
            </Breadcrumb>
          </div>

          <Button asChild variant="ghost" size="sm" className="hidden shrink-0 sm:inline-flex">
            <Link to="/about">
              <Badge variant="outline" className="border-primary/20 bg-primary/5 text-primary">
                <ShieldCheck aria-hidden="true" />
                试点验证版
              </Badge>
            </Link>
          </Button>
        </header>

        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <div className="mx-auto w-full max-w-7xl">
            <Outlet />
          </div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}

export default AppShell;

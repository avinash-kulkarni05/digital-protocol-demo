import { useState, useMemo } from "react";
import { Link, useLocation, useSearch } from "wouter";
import { cn } from "@/lib/utils";
import { 
  FileText, 
  Activity, 
  Users, 
  TestTube, 
  AlertTriangle, 
  Pill, 
  Microscope, 
  FileSignature, 
  Database,
  LayoutDashboard,
  ClipboardList,
  FlaskConical,
  Truck,
  ShieldCheck,
  LogOut,
  Scan,
  Syringe,
  PanelLeftClose,
  PanelLeftOpen,
  ChevronRight,
  Table2,
} from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const navItems = [
  { id: "dashboard", label: "Overview", icon: LayoutDashboard, path: "/" },
  { id: "study_metadata", label: "Study Metadata", icon: FileText, path: "/review/study_metadata" },
  { id: "study_population", label: "Population", icon: Users, path: "/review/study_population" },
  { id: "arms_design", label: "Arms & Design", icon: TestTube, path: "/review/arms_design" },
  { id: "endpoints", label: "Endpoints", icon: Activity, path: "/review/endpoints" },
  { id: "safety", label: "Safety & AEs", icon: AlertTriangle, path: "/review/safety" },
  { id: "safety_decisions", label: "Safety Decisions", icon: ShieldCheck, path: "/review/safety_decision_points" },
  { id: "medications", label: "Concomitant Meds", icon: Pill, path: "/review/medications" },
  { id: "biospecimen", label: "Biospecimen", icon: Microscope, path: "/review/biospecimen" },
  { id: "lab_specs", label: "Lab Specs", icon: FlaskConical, path: "/review/laboratory_specifications" },
  { id: "consent", label: "Informed Consent", icon: FileSignature, path: "/review/consent" },
  { id: "pro", label: "PRO Specs", icon: ClipboardList, path: "/review/pro_specifications" },
  { id: "data_mgmt", label: "Data Management", icon: Database, path: "/review/data_management" },
  { id: "logistics", label: "Site Logistics", icon: Truck, path: "/review/site_operations_logistics" },
  { id: "quality", label: "Quality Mgmt", icon: ShieldCheck, path: "/review/quality_management" },
  { id: "withdrawal", label: "Withdrawal", icon: LogOut, path: "/review/withdrawal_procedures" },
  { id: "imaging", label: "Imaging", icon: Scan, path: "/review/imaging_central_reading" },
  { id: "pkpd", label: "PK/PD Sampling", icon: Syringe, path: "/review/pkpd_sampling" },
  { id: "soa_analysis", label: "SOA Analysis", icon: Table2, path: "/soa-analysis" },
  { id: "eligibility_analysis", label: "Eligibility Analysis", icon: Users, path: "/eligibility-analysis" },
];

export function Sidebar() {
  const [location] = useLocation();
  const searchString = useSearch();
  const [isCollapsed, setIsCollapsed] = useState(false);

  const currentStudyId = useMemo(() => {
    const searchParams = new URLSearchParams(searchString);
    return searchParams.get('studyId');
  }, [searchString]);

  const currentProtocolId = useMemo(() => {
    const searchParams = new URLSearchParams(searchString);
    return searchParams.get('protocolId');
  }, [searchString]);

  const getPathWithStudyId = (path: string) => {
    if (path === "/") return path;

    const params = new URLSearchParams();
    if (currentStudyId) {
      params.set('studyId', currentStudyId);
    }
    // Also pass protocolId for SOA and Eligibility pages
    if (currentProtocolId && (path === '/soa-analysis' || path === '/eligibility-analysis')) {
      params.set('protocolId', currentProtocolId);
    }

    const queryString = params.toString();
    return queryString ? `${path}?${queryString}` : path;
  };

  return (
    <div 
      className={cn(
        "h-screen bg-sidebar border-r border-sidebar-border flex flex-col shrink-0 transition-all duration-300 ease-in-out relative group/sidebar",
        isCollapsed ? "w-[70px]" : "w-64"
      )}
    >
      <Link href="/" className={cn("flex items-center gap-3 cursor-pointer hover:opacity-80 transition-opacity", isCollapsed ? "p-4 justify-center" : "p-6")}>
        <div className="w-8 h-8 rounded-lg bg-gray-900 flex items-center justify-center text-white font-bold shadow-md shadow-gray-500/20 shrink-0">
          P
        </div>
        {!isCollapsed && (
          <span className="font-semibold text-lg tracking-tight animate-in fade-in duration-300">ProtocolReview</span>
        )}
      </Link>

      <Button
        variant="ghost"
        size="icon"
        className={cn(
          "absolute -right-3 top-7 z-20 h-6 w-6 rounded-full border bg-background shadow-sm hover:bg-accent text-muted-foreground opacity-0 group-hover/sidebar:opacity-100 transition-opacity",
          isCollapsed && "rotate-180"
        )}
        onClick={() => setIsCollapsed(!isCollapsed)}
      >
        <PanelLeftClose className="h-3 w-3" />
      </Button>

      <div className="flex-1 min-h-0">
        <ScrollArea className="h-full px-3 py-2">
          {!isCollapsed && (
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2 px-2 animate-in fade-in duration-300">
              Protocol Extraction
            </div>
          )}
          {isCollapsed && (
             <div className="h-px bg-sidebar-border mx-2 mb-4" />
          )}
          
          <nav className="space-y-1 pb-4">
            <TooltipProvider delayDuration={0}>
              {navItems.map((item) => {
                const isActive = location === item.path || (item.path !== "/" && location.startsWith(item.path));
                const Icon = item.icon;
                
                const LinkContent = (
                  <Link 
                    key={item.id} 
                    href={getPathWithStudyId(item.path)}
                    className={cn(
                      "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-all duration-200 cursor-pointer group",
                      isActive 
                        ? "bg-sidebar-accent text-primary font-semibold shadow-sm" 
                        : "text-muted-foreground hover:bg-sidebar-accent/50 hover:text-foreground",
                      isCollapsed && "justify-center px-2"
                    )}
                  >
                    <Icon className={cn("w-4 h-4 shrink-0 transition-colors", isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground")} />
                    {!isCollapsed && (
                      <span className="truncate animate-in fade-in duration-200">{item.label}</span>
                    )}
                  </Link>
                );

                if (isCollapsed) {
                  return (
                    <Tooltip key={item.id}>
                      <TooltipTrigger asChild>
                        {LinkContent}
                      </TooltipTrigger>
                      <TooltipContent side="right" className="flex items-center gap-2 bg-gray-900 text-gray-50 border-gray-800">
                        {item.label}
                      </TooltipContent>
                    </Tooltip>
                  );
                }

                return LinkContent;
              })}
            </TooltipProvider>
          </nav>
        </ScrollArea>
      </div>
    </div>
  );
}
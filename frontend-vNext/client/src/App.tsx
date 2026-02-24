import { Switch, Route } from "wouter";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { Toaster } from "@/components/ui/toaster";
import LandingPage from "@/pages/LandingPage";
import ReviewPage from "@/pages/ReviewPage";
import SOAAnalysisPage from "@/pages/SOAAnalysisPage";
import QEBValidationWizardPage from "@/pages/QEBValidationWizardPage";
import SiteFeasibilityPage from "@/pages/SiteFeasibilityPage";
import InsightsReviewShell from "@/pages/InsightsReviewShell";
import NotFound from "@/pages/not-found";
import { CoverageVerificationPanel } from "@/components/CoverageVerificationPanel";

function LandingLayout() {
  return (
    <div className="h-screen w-full bg-background text-foreground font-sans selection:bg-primary/20 overflow-auto">
      <LandingPage />
    </div>
  );
}

function AppLayout() {
  return (
    <div className="flex h-screen w-full bg-background text-foreground font-sans selection:bg-primary/20">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header title="TROPION-LUNG01 Review" />
        <main className="flex-1 overflow-auto relative">
          <Switch>
            <Route path="/review/:section" component={ReviewPage} />
            <Route path="/soa-analysis" component={SOAAnalysisPage} />
            <Route path="/eligibility-analysis" component={QEBValidationWizardPage} />
            <Route path="/site-feasibility" component={SiteFeasibilityPage} />
            <Route path="/insights" component={InsightsReviewShell} />
            <Route component={NotFound} />
          </Switch>
        </main>
      </div>
    </div>
  );
}

function App() {
  return (
    <>
      <Switch>
        <Route path="/" component={LandingLayout} />
        <Route path="/dev/coverage-verification" component={CoverageVerificationPanel} />
        <Route>
          <AppLayout />
        </Route>
      </Switch>
      <Toaster />
    </>
  );
}

export default App;

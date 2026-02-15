import { Switch, Route } from "wouter";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { Toaster } from "@/components/ui/toaster";
import LandingPage from "@/pages/LandingPage";
import LoginPage from "@/pages/LoginPage";
import ReviewPage from "@/pages/ReviewPage";
import SOAAnalysisPage from "@/pages/SOAAnalysisPage";
import QEBValidationWizardPage from "@/pages/QEBValidationWizardPage";
import SiteFeasibilityPage from "@/pages/SiteFeasibilityPage";
import InsightsReviewShell from "@/pages/InsightsReviewShell";
import NotFound from "@/pages/not-found";
import { CoverageVerificationPanel } from "@/components/CoverageVerificationPanel";
import { AuthProvider, useAuth } from "@/lib/auth";

function LandingLayout() {
  return (
    <div className="h-screen w-full bg-background text-foreground font-sans selection:bg-primary/20 overflow-auto">
      <LandingPage />
    </div>
  );
}

function AppLayout() {
  const { user, logout } = useAuth();
  return (
    <div className="flex h-screen w-full bg-background text-foreground font-sans selection:bg-primary/20">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header title="Protocol Review" userEmail={user?.email} onLogout={logout} />
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

function AuthenticatedApp() {
  const { user, checking, login } = useAuth();

  if (checking) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-neutral-50">
        <div className="animate-spin h-8 w-8 border-4 border-neutral-300 border-t-neutral-900 rounded-full" />
      </div>
    );
  }

  if (!user) {
    return <LoginPage onLogin={login} />;
  }

  return (
    <Switch>
      <Route path="/" component={LandingLayout} />
      <Route path="/dev/coverage-verification" component={CoverageVerificationPanel} />
      <Route>
        <AppLayout />
      </Route>
    </Switch>
  );
}

function App() {
  return (
    <AuthProvider>
      <AuthenticatedApp />
      <Toaster />
    </AuthProvider>
  );
}

export default App;

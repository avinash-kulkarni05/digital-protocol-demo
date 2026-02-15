import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Loader2, LogIn, AlertCircle } from "lucide-react";

interface LoginPageProps {
  onLogin: (user: { email: string }) => void;
}

export default function LoginPage({ onLogin }: LoginPageProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.error || "Login failed");
        return;
      }

      onLogin(data.user);
    } catch {
      setError("Unable to connect. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-gradient-to-br from-neutral-50 to-neutral-100">
      <div className="w-full max-w-md px-6">
        <div className="text-center mb-10">
          <div className="flex items-center justify-center gap-2 mb-6">
            <img
              src="/saama-logo.svg"
              alt="Saama"
              className="h-8"
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = "none";
              }}
            />
            <span className="text-xl font-semibold text-neutral-400 ml-1">|</span>
            <span className="text-lg text-neutral-600">Digital Study Platform</span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-neutral-900 mb-2">
            Welcome Back
          </h1>
          <p className="text-neutral-500 text-sm">
            Sign in with your Saama credentials to continue
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {error && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="space-y-1.5">
            <label htmlFor="email" className="block text-sm font-medium text-neutral-700">
              Email Address
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@saama.com"
              required
              autoFocus
              className="w-full px-4 py-2.5 rounded-lg border border-neutral-300 bg-white text-neutral-900 placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:border-transparent transition-all text-sm"
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="password" className="block text-sm font-medium text-neutral-700">
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              required
              className="w-full px-4 py-2.5 rounded-lg border border-neutral-300 bg-white text-neutral-900 placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:border-transparent transition-all text-sm"
            />
          </div>

          <Button
            type="submit"
            disabled={isLoading}
            className="w-full h-11 bg-neutral-900 hover:bg-neutral-800 text-white rounded-lg font-medium text-sm transition-colors"
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <LogIn className="h-4 w-4 mr-2" />
            )}
            {isLoading ? "Signing in..." : "Sign In"}
          </Button>
        </form>

        <p className="text-center text-xs text-neutral-400 mt-8">
          Access restricted to authorized Saama personnel
        </p>
      </div>
    </div>
  );
}

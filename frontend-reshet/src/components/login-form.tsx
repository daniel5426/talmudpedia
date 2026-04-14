"use client"
import { cn } from "@/lib/utils"
import { useState } from "react"
import { useRouter } from "next/navigation"
import { authService } from "@/services"
import { GoogleLogin } from "@react-oauth/google"
import Link from "next/link"
import Image from "next/image"
import { useAuthAccess } from "@/components/auth/auth-access-context"
import { LegalLinks } from "@/components/auth/legal-links"
import { BetaAccessPanel } from "@/components/marketing/beta-access-panel"
import { applyAuthSession, clearAuthSession } from "@/lib/auth-session"

export function LoginForm({
  className,
  ...props
}: React.ComponentProps<"div">) {
  const { authUnlocked } = useAuthAccess()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const router = useRouter()
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)

    try {
      const session = await authService.login(email, password)
      applyAuthSession(session)
      router.push("/admin/agents/playground")
    } catch (err: any) {
      setError(err.message || "Login failed")
      clearAuthSession()
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleSuccess = async (credentialResponse: any) => {
    if (!credentialResponse.credential) return;
    setLoading(true);
    setError("");
    try {
      const session = await authService.googleLogin(credentialResponse.credential);
      applyAuthSession(session);
      router.push("/admin/agents/playground");
    } catch (err: any) {
      setError(err.message || "Google login failed");
      clearAuthSession();
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={cn("flex flex-1 flex-col", className)} {...props}>
      {/* Top bar */}
      <div className="flex items-center justify-between px-8 py-6">
        <Link href="/" className="flex items-center gap-2">
          <Image src="/kesher.png" alt="AGENTS24" width={28} height={28} className="w-7 h-7 rounded-lg" />
          <span className="text-sm font-bold tracking-tight text-gray-900">AGENTS24</span>
        </Link>
        {authUnlocked ? (
          <Link
            href="/auth/signup"
            className="text-sm font-medium text-gray-500 hover:text-gray-900 transition-colors"
          >
            Create account
          </Link>
        ) : (
          <Link
            href="/contact"
            className="text-sm font-medium text-gray-500 hover:text-gray-900 transition-colors"
          >
            Contact
          </Link>
        )}
      </div>

      {/* Form area */}
      <div className="flex flex-1 items-center justify-center px-8 py-12">
        {!authUnlocked ? (
          <BetaAccessPanel source="auth-login" />
        ) : (
        <div className="w-full max-w-sm">
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-gray-900 tracking-tight">
              Welcome back
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              Enter your credentials to sign in
            </p>
          </div>

          {error && (
            <div className="mb-4 px-4 py-3 rounded-xl bg-red-50 border border-red-100 text-sm text-red-600">
              {error}
            </div>
          )}

          {/* Google OAuth */}
          <div className="mb-6">
            <div className="flex justify-center">
              <GoogleLogin
                onSuccess={handleGoogleSuccess}
                onError={() => setError("Google Login Failed")}
                theme="outline"
                size="large"
                text="signin_with"
                shape="rectangular"
                width="360"
              />
            </div>
          </div>

          {/* Divider */}
          <div className="relative mb-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-gray-200" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-white px-3 text-gray-400 font-medium tracking-wider">
                Or continue with
              </span>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label htmlFor="email" className="block text-sm font-semibold text-gray-900 mb-1.5">
                Email
              </label>
              <input
                id="email"
                type="email"
                placeholder="name@example.com"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-2.5 rounded-xl border border-gray-200 bg-white text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-900/10 focus:border-gray-300 transition-all"
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label htmlFor="password" className="block text-sm font-semibold text-gray-900">
                  Password
                </label>
                <a href="#" className="text-xs text-gray-400 hover:text-gray-600 transition-colors">
                  Forgot password?
                </a>
              </div>
              <input
                id="password"
                type="password"
                placeholder="Enter your password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-2.5 rounded-xl border border-gray-200 bg-white text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-900/10 focus:border-gray-300 transition-all"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full px-4 py-2.5 rounded-xl bg-[#7c5aed] hover:bg-[#6d4ed4] text-white text-sm font-medium transition-colors disabled:opacity-50"
            >
              {loading ? "Signing in..." : "Sign in"}
            </button>
          </form>

          <p className="text-center text-sm text-gray-500 mt-6">
            Don&apos;t have an account?{" "}
            <Link href="/auth/signup" className="text-[#7c5aed] hover:underline font-medium">
              Create account
            </Link>
          </p>
        </div>
        )}
      </div>

      {/* Bottom terms */}
      <div className="px-8 py-5 text-center">
        {authUnlocked ? (
          <LegalLinks prefix="By signing in, you agree to our" />
        ) : (
          <p className="text-xs text-gray-400">Access is currently reviewed manually.</p>
        )}
      </div>
    </div>
  )
}

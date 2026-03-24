"use client"
import { cn } from "@/lib/utils"
import { useState } from "react"
import { useRouter } from "next/navigation"
import { authService } from "@/services"
import { useAuthStore } from "@/lib/store/useAuthStore"
import { GoogleLogin } from "@react-oauth/google"
import Link from "next/link"

export function SignupForm({
  className,
  ...props
}: React.ComponentProps<"div">) {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [fullName, setFullName] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const router = useRouter()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)

    try {
      await authService.register(email, password, fullName)
      const { access_token } = await authService.login(email, password)
      useAuthStore.getState().setAuth(null as any, access_token)
      const user = await authService.getProfile()
      useAuthStore.getState().setAuth(user, access_token)
      router.push("/admin/agents/playground")
    } catch (err: any) {
      setError(err.message || "Registration failed")
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleSuccess = async (credentialResponse: any) => {
    if (!credentialResponse.credential) return;
    setLoading(true);
    setError("");
    try {
      const { access_token } = await authService.googleLogin(credentialResponse.credential);
      useAuthStore.getState().setAuth(null as any, access_token);
      const user = await authService.getProfile();
      useAuthStore.getState().setAuth(user, access_token);
      router.push("/admin/agents/playground");
    } catch (err: any) {
      setError(err.message || "Google signup failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={cn("flex flex-1 flex-col", className)} {...props}>
      {/* Top bar */}
      <div className="flex items-center justify-between px-8 py-6">
        <Link href="/" className="flex items-center gap-2">
          <img src="/kesher.png" alt="AGENTS24" className="w-7 h-7 rounded-lg" />
          <span className="text-sm font-bold tracking-tight text-gray-900">AGENTS24</span>
        </Link>
        <Link
          href="/auth/login"
          className="text-sm font-medium text-gray-500 hover:text-gray-900 transition-colors"
        >
          Sign in
        </Link>
      </div>

      {/* Form area */}
      <div className="flex flex-1 items-center justify-center px-8 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-gray-900 tracking-tight">
              Create account
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              Enter your details to get started
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
                useOneTap
                theme="outline"
                size="large"
                text="signup_with"
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
              <label htmlFor="name" className="block text-sm font-semibold text-gray-900 mb-1.5">
                Full Name
              </label>
              <input
                id="name"
                type="text"
                placeholder="John Doe"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="w-full px-4 py-2.5 rounded-xl border border-gray-200 bg-white text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-900/10 focus:border-gray-300 transition-all"
              />
            </div>

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
              <label htmlFor="password" className="block text-sm font-semibold text-gray-900 mb-1.5">
                Password
              </label>
              <input
                id="password"
                type="password"
                placeholder="Create a password"
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
              {loading ? "Creating account..." : "Create account"}
            </button>
          </form>

          <p className="text-center text-sm text-gray-500 mt-6">
            Already have an account?{" "}
            <Link href="/auth/login" className="text-[#7c5aed] hover:underline font-medium">
              Sign in
            </Link>
          </p>
        </div>
      </div>

      {/* Bottom terms */}
      <div className="px-8 py-5 text-center">
        <p className="text-xs text-gray-400">
          By signing up, you agree to our{" "}
          <a href="#" className="text-[#7c5aed] hover:underline">Terms of Service</a>
          {" "}and{" "}
          <a href="#" className="text-[#7c5aed] hover:underline">Privacy Policy</a>
        </p>
      </div>
    </div>
  )
}

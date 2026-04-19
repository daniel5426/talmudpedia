"use client"
import { cn } from "@/lib/utils"
import Link from "next/link"
import Image from "next/image"
import { useAuthAccess } from "@/components/auth/auth-access-context"
import { LegalLinks } from "@/components/auth/legal-links"
import { BetaAccessPanel } from "@/components/marketing/beta-access-panel"
import { authService } from "@/services"

export function LoginForm({
  className,
  ...props
}: React.ComponentProps<"div">) {
  const { authUnlocked } = useAuthAccess()
  const loginUrl = authService.getLoginUrl("/admin/agents/playground")

  return (
    <div className={cn("flex flex-1 flex-col", className)} {...props}>
      <div className="flex items-center justify-between px-8 py-6">
        <Link href="/" className="flex items-center gap-2">
          <Image src="/kesher.png" alt="AGENTS24" width={28} height={28} className="h-7 w-7 rounded-lg" />
          <span className="text-sm font-bold tracking-tight text-gray-900">AGENTS24</span>
        </Link>
        {authUnlocked ? (
          <Link href="/auth/signup" className="text-sm font-medium text-gray-500 transition-colors hover:text-gray-900">
            Create account
          </Link>
        ) : (
          <Link href="/contact" className="text-sm font-medium text-gray-500 transition-colors hover:text-gray-900">
            Contact
          </Link>
        )}
      </div>

      <div className="flex flex-1 items-center justify-center px-8 py-12">
        {!authUnlocked ? (
          <BetaAccessPanel source="auth-login" />
        ) : (
          <div className="w-full max-w-sm">
            <div className="mb-8">
              <h1 className="text-2xl font-bold tracking-tight text-gray-900">Welcome back</h1>
              <p className="mt-1 text-sm text-gray-500">
                Sign in through the hosted WorkOS flow. Your session will return here automatically.
              </p>
            </div>

            <a
              href={loginUrl}
              className="block w-full rounded-xl bg-[#111827] px-4 py-3 text-center text-sm font-medium text-white transition-colors hover:bg-[#0f172a]"
            >
              Continue to sign in
            </a>

            <p className="mt-6 text-center text-sm text-gray-500">
              Don&apos;t have an account?{" "}
              <Link href="/auth/signup" className="font-medium text-[#111827] hover:underline">
                Create account
              </Link>
            </p>
          </div>
        )}
      </div>

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

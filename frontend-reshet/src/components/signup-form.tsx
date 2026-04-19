"use client"
import { cn } from "@/lib/utils"
import Link from "next/link"
import Image from "next/image"
import { useAuthAccess } from "@/components/auth/auth-access-context"
import { LegalLinks } from "@/components/auth/legal-links"
import { BetaAccessPanel } from "@/components/marketing/beta-access-panel"
import { authService } from "@/services"

export function SignupForm({
  className,
  ...props
}: React.ComponentProps<"div">) {
  const { authUnlocked } = useAuthAccess()
  const signupUrl = authService.getSignupUrl("/admin/agents/playground")

  return (
    <div className={cn("flex flex-1 flex-col", className)} {...props}>
      <div className="flex items-center justify-between px-8 py-6">
        <Link href="/" className="flex items-center gap-2">
          <Image src="/kesher.png" alt="AGENTS24" width={28} height={28} className="h-7 w-7 rounded-lg" />
          <span className="text-sm font-bold tracking-tight text-gray-900">AGENTS24</span>
        </Link>
        {authUnlocked ? (
          <Link href="/auth/login" className="text-sm font-medium text-gray-500 transition-colors hover:text-gray-900">
            Sign in
          </Link>
        ) : (
          <Link href="/contact" className="text-sm font-medium text-gray-500 transition-colors hover:text-gray-900">
            Contact
          </Link>
        )}
      </div>

      <div className="flex flex-1 items-center justify-center px-8 py-12">
        {!authUnlocked ? (
          <BetaAccessPanel source="auth-signup" />
        ) : (
          <div className="w-full max-w-sm">
            <div className="mb-8">
              <h1 className="text-2xl font-bold tracking-tight text-gray-900">Create account</h1>
              <p className="mt-1 text-sm text-gray-500">
                Sign up through the hosted WorkOS flow. Organization setup continues after the callback.
              </p>
            </div>

            <a
              href={signupUrl}
              className="block w-full rounded-xl bg-[#111827] px-4 py-3 text-center text-sm font-medium text-white transition-colors hover:bg-[#0f172a]"
            >
              Continue to sign up
            </a>

            <p className="mt-6 text-center text-sm text-gray-500">
              Already have an account?{" "}
              <Link href="/auth/login" className="font-medium text-[#111827] hover:underline">
                Sign in
              </Link>
            </p>
          </div>
        )}
      </div>

      <div className="px-8 py-5 text-center">
        {authUnlocked ? (
          <LegalLinks prefix="By signing up, you agree to our" />
        ) : (
          <p className="text-xs text-gray-400">Access is currently reviewed manually.</p>
        )}
      </div>
    </div>
  )
}

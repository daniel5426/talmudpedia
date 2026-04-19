"use client"

import { FormEvent, useEffect, useMemo, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"

import { applyAuthSession } from "@/lib/auth-session"
import { useAuthStore } from "@/lib/store/useAuthStore"
import { authService } from "@/services/auth"

function navigateToTarget(router: ReturnType<typeof useRouter>, target: string) {
  if (/^https?:\/\//i.test(target)) {
    window.location.assign(target)
    return
  }
  router.replace(target)
}

export default function AuthOnboardingPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const hydrated = useAuthStore((state) => state.hydrated)
  const sessionChecked = useAuthStore((state) => state.sessionChecked)
  const user = useAuthStore((state) => state.user)
  const onboardingRequired = useAuthStore((state) => state.onboardingRequired)
  const [name, setName] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const returnTo = useMemo(
    () => searchParams.get("return_to") || "/admin/agents/playground",
    [searchParams],
  )

  useEffect(() => {
    if (!hydrated || !sessionChecked) {
      return
    }
    if (!user) {
      router.replace(`/auth/login?return_to=${encodeURIComponent(returnTo)}`)
      return
    }
    if (!onboardingRequired) {
      navigateToTarget(router, returnTo)
    }
  }, [hydrated, onboardingRequired, returnTo, router, sessionChecked, user])

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const result = await authService.createOnboardingOrganization(name, returnTo)
      if ("redirect_url" in result) {
        window.location.assign(result.redirect_url)
        return
      }
      applyAuthSession(result)
      navigateToTarget(router, returnTo)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create organization")
    } finally {
      setSubmitting(false)
    }
  }

  if (!hydrated || !sessionChecked || !user || !onboardingRequired) {
    return null
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-lg items-center px-6 py-12">
      <div className="w-full rounded-2xl border border-border bg-card p-8 shadow-sm">
        <div className="mb-6 space-y-2">
          <h1 className="text-2xl font-semibold tracking-tight">Create your organization</h1>
          <p className="text-sm text-muted-foreground">
            You are signed in as {user.email}. Create your first organization to continue.
          </p>
        </div>
        <form className="space-y-4" onSubmit={handleSubmit}>
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="organization-name">
              Organization name
            </label>
            <input
              id="organization-name"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-offset-background focus-visible:ring-2 focus-visible:ring-ring"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Acme"
              required
            />
          </div>
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
          <button
            type="submit"
            disabled={submitting}
            className="inline-flex w-full items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60"
          >
            {submitting ? "Creating..." : "Create organization"}
          </button>
        </form>
      </div>
    </div>
  )
}

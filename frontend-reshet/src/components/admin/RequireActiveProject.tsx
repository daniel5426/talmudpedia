"use client"

import { useEffect, useRef, useState } from "react"
import { FolderKanban, Loader2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { useAuthStore } from "@/lib/store/useAuthStore"
import { authService, isAuthSessionRedirectResponse, navigateToAuthRedirect } from "@/services/auth"
import { applyAuthSession } from "@/lib/auth-session"

export function RequireActiveProject({ children }: { children: React.ReactNode }) {
  const currentProject = useAuthStore((state) => state.activeProject)
  const hydrated = useAuthStore((state) => state.hydrated)
  const sessionChecked = useAuthStore((state) => state.sessionChecked)
  const user = useAuthStore((state) => state.user)
  const [isReconciling, setIsReconciling] = useState(false)
  const hasAttemptedRefresh = useRef(false)

  useEffect(() => {
    if (!hydrated || !sessionChecked || !user || currentProject || hasAttemptedRefresh.current) {
      return
    }

    hasAttemptedRefresh.current = true
    setIsReconciling(true)
    void authService
      .getCurrentSession()
      .then((session) => {
        if (isAuthSessionRedirectResponse(session)) {
          navigateToAuthRedirect(session.redirect_url)
          return
        }
        applyAuthSession(session)
      })
      .finally(() => {
        setIsReconciling(false)
      })
  }, [currentProject, hydrated, sessionChecked, user])

  if (!user || !hydrated || !sessionChecked) {
    return <>{children}</>
  }

  if (isReconciling) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  if (!currentProject) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6">
        <div className="w-full max-w-md rounded-2xl border border-border/60 bg-card p-6 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-muted">
            <FolderKanban className="h-6 w-6 text-muted-foreground" />
          </div>
          <h1 className="text-lg font-semibold text-foreground">Active project required</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Agents are project-scoped. Select a project from the organization switcher, then retry.
          </p>
          <div className="mt-5">
            <Button variant="outline" onClick={() => {
              hasAttemptedRefresh.current = false
              setIsReconciling(true)
              void authService
                .getCurrentSession()
                .then((session) => {
                  if (isAuthSessionRedirectResponse(session)) {
                    navigateToAuthRedirect(session.redirect_url)
                    return
                  }
                  applyAuthSession(session)
                })
                .finally(() => setIsReconciling(false))
            }}>
              Retry session sync
            </Button>
          </div>
        </div>
      </div>
    )
  }

  return <>{children}</>
}

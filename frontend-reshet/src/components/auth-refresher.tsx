"use client"

import { useEffect, useRef } from "react"
import { useAuthStore } from "@/lib/store/useAuthStore"
import { authService } from "@/services/auth"
import { HttpRequestError, HttpRequestTimeoutError } from "@/services/http"
import { applyAuthSession, clearAuthSession } from "@/lib/auth-session"

export function AuthRefresher() {
    const hydrated = useAuthStore((state) => state.hydrated)
    const markSessionChecked = useAuthStore((state) => state.markSessionChecked)
    const hasRefreshed = useRef(false)

    useEffect(() => {
        if (!hydrated || hasRefreshed.current) return

        const refreshSession = async () => {
            try {
                hasRefreshed.current = true
                const session = await authService.getCurrentSession()
                applyAuthSession(session)
            } catch (error) {
                if (error instanceof HttpRequestError && error.status === 401) {
                    clearAuthSession()
                } else if (error instanceof HttpRequestTimeoutError) {
                    console.error("Timed out while refreshing browser session", error)
                } else {
                    console.error("Failed to refresh browser session", error)
                }
            } finally {
                markSessionChecked()
            }
        }

        refreshSession()
    }, [hydrated, markSessionChecked])

    return null
}

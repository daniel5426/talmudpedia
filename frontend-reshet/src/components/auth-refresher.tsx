"use client"

import { useEffect, useRef } from "react"
import { useAuthStore } from "@/lib/store/useAuthStore"
import { authService } from "@/services/auth"

export function AuthRefresher() {
    const { token, setAuth, logout } = useAuthStore()
    const hasRefreshed = useRef(false)

    useEffect(() => {
        // Only run if we have a token and haven't refreshed yet this session
        if (!token || hasRefreshed.current) return

        const refreshProfile = async () => {
            try {
                hasRefreshed.current = true
                const user = await authService.getProfile()
                // Update store with fresh user data (preserving token)
                setAuth(user, token)
                console.log("DEBUG: Profile refreshed with org_role:", user.org_role)
            } catch (error) {
                console.error("Failed to refresh profile", error)
                // If 401, we should probably logout, but let's be careful not to loop
                // logout() 
            }
        }

        refreshProfile()
    }, [token, setAuth])

    return null
}

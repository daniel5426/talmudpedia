"use client"

import { type ComponentPropsWithoutRef, type ReactNode, useEffect, useRef, useState } from "react"

import { cn } from "@/lib/utils"

type AdminPageHeaderProps = ComponentPropsWithoutRef<"header"> & {
  children: ReactNode
  contentClassName?: string
}

function isScrollable(element: HTMLElement) {
  const style = window.getComputedStyle(element)
  return /(auto|scroll|overlay)/.test(style.overflowY || style.overflow)
}

export function AdminPageHeader({
  children,
  className,
  contentClassName,
  ...props
}: AdminPageHeaderProps) {
  const headerRef = useRef<HTMLElement | null>(null)
  const [isScrolled, setIsScrolled] = useState(false)

  useEffect(() => {
    const header = headerRef.current
    if (!header) return

    const sibling = header.nextElementSibling
    let targets = new Set<HTMLElement | Window>()

    const syncScrollState = () => {
      setIsScrolled(
        Array.from(targets).some((target) =>
          target === window ? window.scrollY > 0 : target.scrollTop > 0,
        ),
      )
    }

    const collectTargets = () => {
      const nextTargets = new Set<HTMLElement | Window>()

      if (sibling instanceof HTMLElement) {
        if (sibling.matches("[data-admin-page-scroll]") && isScrollable(sibling)) {
          nextTargets.add(sibling)
        }
        if (isScrollable(sibling)) {
          nextTargets.add(sibling)
        }
        sibling
          .querySelectorAll<HTMLElement>("[data-admin-page-scroll], .admin-page-scroll")
          .forEach((element) => {
            if (isScrollable(element)) {
              nextTargets.add(element)
            }
          })
      }

      if (nextTargets.size === 0) {
        nextTargets.add(window)
      }

      return nextTargets
    }

    const bindTargets = () => {
      const nextTargets = collectTargets()
      const hasChanged =
        nextTargets.size !== targets.size ||
        Array.from(nextTargets).some((target) => !targets.has(target))

      if (!hasChanged) {
        syncScrollState()
        return
      }

      targets.forEach((target) => {
        target.removeEventListener("scroll", syncScrollState)
      })

      targets = nextTargets

      targets.forEach((target) => {
        target.addEventListener("scroll", syncScrollState, { passive: true })
      })

      syncScrollState()
    }

    bindTargets()

    const observer =
      sibling instanceof HTMLElement
        ? new MutationObserver(() => {
            bindTargets()
          })
        : null

    observer?.observe(sibling, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class", "style", "data-admin-page-scroll"],
    })

    return () => {
      observer?.disconnect()
      targets.forEach((target) => {
        target.removeEventListener("scroll", syncScrollState)
      })
    }
  }, [])

  return (
    <header
      ref={headerRef}
      className={cn(
        "relative z-30 shrink-0 overflow-visible bg-background/100 supports-[backdrop-filter]:bg-background/100 transition-[background-color,backdrop-filter] duration-300",
        isScrolled &&
          "bg-background/80 backdrop-blur-md supports-[backdrop-filter]:bg-background/65",
        className,
      )}
      {...props}
    >
      <div className={cn("flex h-12 items-center justify-between gap-4 px-3", contentClassName)}>
        {children}
      </div>
      <div
        aria-hidden="true"
        className={cn(
          "pointer-events-none absolute inset-x-0 top-full z-10 h-5 bg-gradient-to-b from-background via-background/95 to-transparent transition-opacity duration-0 supports-[backdrop-filter]:from-background supports-[backdrop-filter]:via-background/70",
          isScrolled ? "opacity-100" : "opacity-0",
        )}
      />
    </header>
  )
}

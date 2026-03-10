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
    const targets = new Set<HTMLElement | Window>()

    if (sibling instanceof HTMLElement) {
      if (sibling.matches("[data-admin-page-scroll]") && isScrollable(sibling)) {
        targets.add(sibling)
      }
      if (isScrollable(sibling)) {
        targets.add(sibling)
      }
      sibling
        .querySelectorAll<HTMLElement>("[data-admin-page-scroll]")
        .forEach((element) => {
          if (isScrollable(element)) {
            targets.add(element)
          }
        })
    }

    if (targets.size === 0) {
      targets.add(window)
    }

    const syncScrollState = () => {
      setIsScrolled(
        Array.from(targets).some((target) =>
          target === window ? window.scrollY > 0 : target.scrollTop > 0,
        ),
      )
    }

    syncScrollState()
    targets.forEach((target) => {
      target.addEventListener("scroll", syncScrollState, { passive: true })
    })

    return () => {
      targets.forEach((target) => {
        target.removeEventListener("scroll", syncScrollState)
      })
    }
  }, [])

  return (
    <header
      ref={headerRef}
      className={cn(
        "shrink-0 border-b border-transparent bg-background/100 supports-[backdrop-filter]:bg-background/100 transition-[background-color,border-color,backdrop-filter,box-shadow] duration-300",
        isScrolled &&
          "border-border/40 bg-background/80 shadow-[0_10px_30px_-26px_hsl(var(--foreground)/0.55)] backdrop-blur-md supports-[backdrop-filter]:bg-background/65",
        className,
      )}
      {...props}
    >
      <div className={cn("flex h-12 items-center justify-between gap-4 px-4", contentClassName)}>
        {children}
      </div>
    </header>
  )
}

"use client"

import type { ComponentPropsWithoutRef, CSSProperties } from "react"

import { cn } from "@/lib/utils"

const KESHER_LOGO_MASK_URL = 'url("/kesher.png")'

export type KesherLogoProps = Omit<ComponentPropsWithoutRef<"span">, "children"> & {
  size?: number | string
}

export function KesherLogo({ className, size, style, ...props }: KesherLogoProps) {
  const dimension = typeof size === "number" ? `${size}px` : size
  const logoStyle: CSSProperties = {
    width: dimension,
    height: dimension,
    backgroundColor: "currentColor",
    WebkitMaskImage: KESHER_LOGO_MASK_URL,
    maskImage: KESHER_LOGO_MASK_URL,
    WebkitMaskRepeat: "no-repeat",
    maskRepeat: "no-repeat",
    WebkitMaskPosition: "center",
    maskPosition: "center",
    WebkitMaskSize: "contain",
    maskSize: "contain",
    ...style,
  }

  return (
    <span
      aria-hidden="true"
      className={cn("inline-block h-5 w-5 shrink-0 text-current", className)}
      style={logoStyle}
      {...props}
    />
  )
}



import Link from "next/link"
import { SlashIcon } from "lucide-react"
import React from "react"

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"

export interface BreadcrumbItemProps {
  label: string
  href?: string
  active?: boolean
  statusDot?: "primary"
}

interface CustomBreadcrumbProps {
  items: BreadcrumbItemProps[]
}

export function CustomBreadcrumb({ items }: CustomBreadcrumbProps) {
  return (
    <Breadcrumb>
      <BreadcrumbList>
        {items.map((item, index) => (
          <React.Fragment key={index}>
            <BreadcrumbItem>
              {item.active ? (
                <BreadcrumbPage className="inline-flex items-center gap-2">
                  <span>{item.label}</span>
                  {item.statusDot === "primary" ? <span className="h-2 w-2 rounded-full bg-primary" /> : null}
                </BreadcrumbPage>
              ) : (
                <BreadcrumbLink asChild>
                  <Link href={item.href || "#"} className="inline-flex items-center gap-2">
                    <span>{item.label}</span>
                    {item.statusDot === "primary" ? <span className="h-2 w-2 rounded-full bg-primary" /> : null}
                  </Link>
                </BreadcrumbLink>
              )}
            </BreadcrumbItem>
            {index < items.length - 1 && (
              <BreadcrumbSeparator>
                <SlashIcon />
              </BreadcrumbSeparator>
            )}
          </React.Fragment>
        ))}
      </BreadcrumbList>
    </Breadcrumb>
  )
}



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
    <Breadcrumb className="max-w-full min-w-0">
      <BreadcrumbList className="max-w-full min-w-0 flex-nowrap">
        {items.map((item, index) => (
          <React.Fragment key={index}>
            <BreadcrumbItem className="min-w-0 max-w-full">
              {item.active ? (
                <BreadcrumbPage className="inline-flex max-w-full min-w-0 items-center gap-2">
                  <span className="block max-w-[12rem] truncate sm:max-w-[18rem] md:max-w-[24rem]" title={item.label}>
                    {item.label}
                  </span>
                  {item.statusDot === "primary" ? <span className="h-2 w-2 rounded-full bg-primary" /> : null}
                </BreadcrumbPage>
              ) : (
                <BreadcrumbLink asChild>
                  <Link href={item.href || "#"} className="inline-flex max-w-full min-w-0 items-center gap-2">
                    <span className="block max-w-[12rem] truncate sm:max-w-[18rem] md:max-w-[24rem]" title={item.label}>
                      {item.label}
                    </span>
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

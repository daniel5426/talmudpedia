import React from "react";
import { SlashIcon } from "lucide-react";

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";

export interface BreadcrumbItemProps {
  label: string;
  href?: string;
  active?: boolean;
  statusDot?: "primary";
}

interface CustomBreadcrumbProps {
  items: BreadcrumbItemProps[];
}

export function CustomBreadcrumb({ items }: CustomBreadcrumbProps) {
  return (
    <Breadcrumb>
      <BreadcrumbList>
        {items.map((item, index) => (
          <React.Fragment key={`${item.label}-${index}`}>
            <BreadcrumbItem>
              {item.active ? (
                <BreadcrumbPage className="inline-flex items-center gap-2">
                  <span>{item.label}</span>
                  {item.statusDot === "primary" ? <span className="h-2 w-2 rounded-full bg-primary" /> : null}
                </BreadcrumbPage>
              ) : (
                <BreadcrumbLink href={item.href || "#"} className="inline-flex items-center gap-2">
                  <span>{item.label}</span>
                  {item.statusDot === "primary" ? <span className="h-2 w-2 rounded-full bg-primary" /> : null}
                </BreadcrumbLink>
              )}
            </BreadcrumbItem>
            {index < items.length - 1 ? (
              <BreadcrumbSeparator>
                <SlashIcon />
              </BreadcrumbSeparator>
            ) : null}
          </React.Fragment>
        ))}
      </BreadcrumbList>
    </Breadcrumb>
  );
}

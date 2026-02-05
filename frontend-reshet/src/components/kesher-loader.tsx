"use client";

import Image from "next/image";
import { cn } from "@/lib/utils";

export type KesherLoaderProps = {
  className?: string;
  size?: number;
};

export function KesherLoader({ className, size = 78 }: KesherLoaderProps) {
  return (
    <div className={cn("flex items-center justify-center", className)}>
      <div className="animate-spin">
        <Image
          src="/kesher.png"
          alt="Kesher"
          width={size}
          height={size}
          className="h-22 w-22 text-muted-foreground/50"
        />
      </div>
    </div>
  );
}


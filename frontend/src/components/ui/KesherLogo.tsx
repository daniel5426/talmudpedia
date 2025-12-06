import Image from "next/image";
import { cn } from "@/lib/utils";

type KesherLogoProps = {
  variant?: "avatar" | "background" | "accent";
  className?: string;
  size?: number;
};

/**
 * Reusable Kesher logo component
 */
export function KesherLogo({ variant = "avatar", className, size }: KesherLogoProps) {
  const baseProps = {
    src: "/kesher.png",
    alt: "Kesher Logo",
    priority: true,
  };

  if (variant === "avatar") {
    return (
      <Image
        {...baseProps}
        width={size || 40}
        height={size || 40}
        className={cn(
          "h-6 w-6 rounded-md object-cover hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground",
          className
        )}
      />
    );
  }

  if (variant === "background") {
    return (
      <Image
        {...baseProps}
        width={1800}
        height={1800}
        className={cn("absolute w-[min(70vw,700px)] opacity-20", className)}
      />
    );
  }

  if (variant === "accent") {
    return (
      <Image
        {...baseProps}
        width={1800}
        height={1800}
        className={cn(
          "absolute w-[min(70vw,200px)] opacity-90 filter brightness-0 invert",
          className
        )}
      />
    );
  }

  return null;
}

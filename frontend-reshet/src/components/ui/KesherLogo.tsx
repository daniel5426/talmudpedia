import Image from "next/image";
import { cn } from "@/lib/utils";

interface KesherLogoProps {
  variant?: "avatar" | "background" | "accent";
  className?: string;
  size?: number;
}

export function KesherLogo({ variant = "avatar", className, size }: KesherLogoProps) {
  const baseProps = {
    src: "/kesher.png",
    alt: "Kesher Logo",
    priority: true,
  };

  // Common mask style to color the PNG based on the theme
  const maskStyle = {
    maskImage: "url(/kesher.png)",
    WebkitMaskImage: "url(/kesher.png)",
    maskSize: "contain",
    WebkitMaskSize: "contain",
    maskRepeat: "no-repeat",
    WebkitMaskRepeat: "no-repeat",
    maskPosition: "center",
    WebkitMaskPosition: "center",
  };

  if (variant === "avatar") {
    return (
      <div
        className={cn(
          "h-6 w-6 rounded-md bg-primary shrink-0 transition-colors hover:bg-primary/80",
          className
        )}
        style={{
          ...maskStyle,
          width: size,
          height: size,
        }}
        role="img"
        aria-label="Kesher Logo"
      />
    );
  }

  if (variant === "background") {
    return (
      <div
        className={cn(
          "absolute w-[min(70vw,700px)] aspect-square opacity-20 bg-primary pointer-events-none",
          className
        )}
        style={maskStyle}
        role="presentation"
      />
    );
  }

  // The "white" version remains unchanged using the filter approach
  if (variant === "accent") {
    return (
      <Image
        {...baseProps}
        width={1800}
        height={1800}
        className={cn(
          "absolute w-[min(70vw,200px)] opacity-90 filter brightness-0 invert pointer-events-none",
          className
        )}
      />
    );
  }

  return null;
}
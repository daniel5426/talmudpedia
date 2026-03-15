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
          "h-6 w-6 shrink-0 rounded-md bg-primary transition-colors hover:bg-primary/80",
          className,
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
          "pointer-events-none absolute aspect-square w-[min(70vw,700px)] bg-primary opacity-20",
          className,
        )}
        style={maskStyle}
        role="presentation"
      />
    );
  }

  if (variant === "accent") {
    return (
      <img
        src={baseProps.src}
        alt={baseProps.alt}
        className={cn(
          "pointer-events-none absolute w-[min(70vw,200px)] opacity-90 filter brightness-0 invert",
          className,
        )}
      />
    );
  }

  return null;
}

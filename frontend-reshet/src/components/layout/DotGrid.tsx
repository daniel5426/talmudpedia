"use client";

import { useEffect, useMemo, useRef } from "react";
import { cn } from "@/lib/utils";

type DotGridProps = React.HTMLAttributes<HTMLDivElement> & {
  dotSize?: number;
  gap?: number;
  baseColor?: string;
  activeColor?: string;
  proximity?: number;
  shockRadius?: number;
  shockStrength?: number;
  resistance?: number;
  returnDuration?: number;
};

type DotGridConfig = Required<
  Pick<
    DotGridProps,
    | "dotSize"
    | "gap"
    | "baseColor"
    | "activeColor"
    | "proximity"
    | "shockRadius"
    | "shockStrength"
    | "resistance"
    | "returnDuration"
  >
>;

type PointerState = {
  x: number;
  y: number;
  active: boolean;
};

type ShockWave = {
  x: number;
  y: number;
  radius: number;
  life: number;
};

class DotGridEngine {
  private ctx: CanvasRenderingContext2D;
  private ratio = 1;
  private width = 0;
  private height = 0;
  private pointer: PointerState = { x: 0, y: 0, active: false };
  private shocks: ShockWave[] = [];
  private frame?: number;
  private lastTime?: number;
  private baseRgb: [number, number, number];
  private activeRgb: [number, number, number];

  constructor(
    private canvas: HTMLCanvasElement,
    private container: HTMLDivElement,
    private config: DotGridConfig
  ) {
    const context = canvas.getContext("2d");
    if (!context) {
      throw new Error("DotGrid requires a 2D canvas context");
    }
    this.ctx = context;
    this.baseRgb = this.toRgb(config.baseColor);
    this.activeRgb = this.toRgb(config.activeColor);
    this.syncSize();
  }

  start() {
    this.stop();
    this.frame = requestAnimationFrame(this.render);
  }

  destroy() {
    this.stop();
  }

  syncSize() {
    const bounds = this.container.getBoundingClientRect();
    this.width = bounds.width;
    this.height = bounds.height;
    this.ratio = window.devicePixelRatio || 1;
    this.canvas.width = Math.max(1, this.width * this.ratio);
    this.canvas.height = Math.max(1, this.height * this.ratio);
    this.ctx.setTransform(this.ratio, 0, 0, this.ratio, 0, 0);
  }

  pointerMove(clientX: number, clientY: number) {
    const point = this.resolvePoint(clientX, clientY);
    if (!point) {
      this.pointer.active = false;
      return;
    }
    this.pointer = { ...point, active: true };
  }

  pointerDown(clientX: number, clientY: number) {
    const point = this.resolvePoint(clientX, clientY);
    if (!point) {
      return;
    }
    this.pointer = { ...point, active: true };
    this.addShock(point.x, point.y);
  }

  pointerLeave() {
    this.pointer.active = false;
  }

  private stop() {
    if (this.frame) {
      cancelAnimationFrame(this.frame);
      this.frame = undefined;
    }
    this.lastTime = undefined;
  }

  private render = (timestamp: number) => {
    const delta =
      this.lastTime !== undefined ? (timestamp - this.lastTime) / 1000 : 0;
    this.lastTime = timestamp;
    this.drawFrame();
    this.updateShocks(delta);
    this.frame = requestAnimationFrame(this.render);
  };

  private drawFrame() {
    this.ctx.clearRect(0, 0, this.width, this.height);
    const offset = this.config.gap / 2;
    for (let y = offset; y < this.height + offset; y += this.config.gap) {
      for (let x = offset; x < this.width + offset; x += this.config.gap) {
        const pointerInfluence = this.pointer.active
          ? Math.max(
              0,
              1 -
                this.distance(x, y, this.pointer.x, this.pointer.y) /
                  this.config.proximity
            )
          : 0;
        const shockInfluence = this.computeShockInfluence(x, y);
        const influence = Math.min(
          1,
          pointerInfluence + shockInfluence * this.config.shockStrength * 0.25
        );
        const radius =
          (this.config.dotSize / 2) * (1 + influence * 0.9);
        this.ctx.beginPath();
        this.ctx.arc(x, y, radius, 0, Math.PI * 2);
        this.ctx.fillStyle = this.mixColor(influence);
        this.ctx.fill();
      }
    }
  }

  private computeShockInfluence(x: number, y: number) {
    if (!this.shocks.length) {
      return 0;
    }
    let influence = 0;
    for (const shock of this.shocks) {
      const dist = this.distance(x, y, shock.x, shock.y);
      const delta = Math.abs(dist - shock.radius);
      const strength = Math.max(0, 1 - delta / this.config.shockRadius);
      influence = Math.max(influence, strength * shock.life);
    }
    return influence;
  }

  private updateShocks(delta: number) {
    if (!delta) {
      return;
    }
    const growth = this.config.shockRadius / this.config.returnDuration;
    const decayRate = (delta / this.config.returnDuration) * (1000 / this.config.resistance);
    this.shocks = this.shocks
      .map((shock) => ({
        ...shock,
        radius: shock.radius + growth * delta,
        life: Math.max(0, shock.life - decayRate),
      }))
      .filter(
        (shock) => shock.radius <= this.config.shockRadius && shock.life > 0
      );
  }

  private addShock(x: number, y: number) {
    this.shocks.push({ x, y, radius: 0, life: 1 });
  }

  private resolvePoint(clientX: number, clientY: number) {
    const rect = this.container.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    if (x < 0 || y < 0 || x > rect.width || y > rect.height) {
      return null;
    }
    return { x, y };
  }

  private distance(x1: number, y1: number, x2: number, y2: number) {
    const dx = x2 - x1;
    const dy = y2 - y1;
    return Math.hypot(dx, dy);
  }

  private mixColor(intensity: number) {
    const clamped = Math.max(0, Math.min(1, intensity));
    const r = Math.round(
      this.baseRgb[0] + (this.activeRgb[0] - this.baseRgb[0]) * clamped
    );
    const g = Math.round(
      this.baseRgb[1] + (this.activeRgb[1] - this.baseRgb[1]) * clamped
    );
    const b = Math.round(
      this.baseRgb[2] + (this.activeRgb[2] - this.baseRgb[2]) * clamped
    );
    return `rgb(${r}, ${g}, ${b})`;
  }

  private toRgb(value: string): [number, number, number] {
    const hex = value.replace("#", "");
    const safeHex = hex.length === 6 ? hex : "ffffff";
    const bigint = Number.parseInt(safeHex, 16);
    return [
      (bigint >> 16) & 255,
      (bigint >> 8) & 255,
      bigint & 255,
    ];
  }
}

export default function DotGrid({
  dotSize = 8,
  gap = 18,
  baseColor = "#1E1B4B",
  activeColor = "#7C3AED",
  proximity = 150,
  shockRadius = 220,
  shockStrength = 4,
  resistance = 600,
  returnDuration = 1.2,
  className,
  style,
  ...rest
}: DotGridProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const config = useMemo(
    () => ({
      dotSize,
      gap,
      baseColor,
      activeColor,
      proximity,
      shockRadius,
      shockStrength,
      resistance,
      returnDuration,
    }),
    [
      dotSize,
      gap,
      baseColor,
      activeColor,
      proximity,
      shockRadius,
      shockStrength,
      resistance,
      returnDuration,
    ]
  );

  useEffect(() => {
    if (
      typeof window === "undefined" ||
      !canvasRef.current ||
      !containerRef.current
    ) {
      return;
    }

    const engine = new DotGridEngine(
      canvasRef.current,
      containerRef.current,
      config
    );
    engine.start();

    const resize = () => engine.syncSize();
    let resizeObserver: ResizeObserver | null = null;

    if (typeof ResizeObserver !== "undefined") {
      resizeObserver = new ResizeObserver(resize);
      resizeObserver.observe(containerRef.current);
    } else {
      window.addEventListener("resize", resize);
    }

    const handlePointerMove = (event: PointerEvent) =>
      engine.pointerMove(event.clientX, event.clientY);
    const handlePointerDown = (event: PointerEvent) =>
      engine.pointerDown(event.clientX, event.clientY);
    const handlePointerLeave = () => engine.pointerLeave();

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("pointerup", handlePointerLeave);
    window.addEventListener("pointerleave", handlePointerLeave);

    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("pointerup", handlePointerLeave);
      window.removeEventListener("pointerleave", handlePointerLeave);
      if (resizeObserver) {
        resizeObserver.disconnect();
      } else {
        window.removeEventListener("resize", resize);
      }
      engine.destroy();
    };
  }, [config]);

  return (
    <div
      ref={containerRef}
      className={cn("h-full w-full pointer-events-none", className)}
      style={{ ...style }}
      {...rest}
    >
      <canvas ref={canvasRef} className="h-full w-full" />
    </div>
  );
}


"use client";

import { useEffect, useRef, useCallback, type MutableRefObject } from "react";

/* ═══════════════════════════════════════════════════════════
   PARTICLE FIELD — Canvas-based dot grid with repulsor physics
   
   Accepts mutable refs for repulsors/clearZones so the parent
   can update them without triggering React re-renders.
   The tick loop reads from the refs each frame.
   ═══════════════════════════════════════════════════════════ */

export type Repulsor = {
  x: number;
  y: number;
  radius: number;
  strength?: number; // multiplier, default 1
};

export type ClearZone = {
  x: number;
  y: number;
  width: number;
  height: number;
  padding?: number; // extra breathing room around the rect
};

type Particle = {
  homeX: number;
  homeY: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  opacity: number;
};

type ParticleFieldProps = {
  /** Mutable ref to circular repulsors (e.g. the logo). Updated by parent without re-renders. */
  repulsorsRef: MutableRefObject<Repulsor[]>;
  /** Mutable ref to rectangular clear zones (text areas). Optional. */
  clearZonesRef?: MutableRefObject<ClearZone[]>;
  /** If true, skip animation and show static dots */
  reducedMotion?: boolean;
  /** CSS class for the container */
  className?: string;
};

// ── Physics constants ──
const SPRING_K = 0.035; // spring stiffness — higher = snappier return
const DAMPING = 0.82; // velocity damping — lower = more overdamped (less bouncing)
const REPULSOR_FORCE = 8;
const PARTICLE_SPACING = 26;
const PARTICLE_BASE_SIZE = 1.3;
const PARTICLE_SIZE_VARIANCE = 0.5;
const PARTICLE_BASE_OPACITY = 0.11;
const PARTICLE_OPACITY_VARIANCE = 0.05;

function createParticles(width: number, height: number): Particle[] {
  const particles: Particle[] = [];
  const cols = Math.ceil(width / PARTICLE_SPACING) + 4;
  const rows = Math.ceil(height / PARTICLE_SPACING) + 4;
  const offsetX = (width - (cols - 1) * PARTICLE_SPACING) / 2;
  const offsetY = (height - (rows - 1) * PARTICLE_SPACING) / 2;

  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      const jitterX = (Math.random() - 0.5) * 5;
      const jitterY = (Math.random() - 0.5) * 5;
      const homeX = offsetX + col * PARTICLE_SPACING + jitterX;
      const homeY = offsetY + row * PARTICLE_SPACING + jitterY;

      particles.push({
        homeX,
        homeY,
        x: homeX,
        y: homeY,
        vx: 0,
        vy: 0,
        size: PARTICLE_BASE_SIZE + Math.random() * PARTICLE_SIZE_VARIANCE,
        opacity: PARTICLE_BASE_OPACITY + Math.random() * PARTICLE_OPACITY_VARIANCE,
      });
    }
  }
  return particles;
}

export function ParticleField({
  repulsorsRef,
  clearZonesRef,
  reducedMotion = false,
  className = "",
}: ParticleFieldProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const particlesRef = useRef<Particle[]>([]);
  const animFrameRef = useRef<number>(0);
  const dprRef = useRef(1);

  const initParticles = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    dprRef.current = dpr;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    particlesRef.current = createParticles(rect.width, rect.height);
  }, []);

  const tick = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const particles = particlesRef.current;
    const reps = repulsorsRef.current;
    const zones = clearZonesRef?.current || [];
    const dpr = dprRef.current;
    const w = canvas.width / dpr;
    const h = canvas.height / dpr;

    // ── Physics step ──
    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];

      // Spring force back to home
      let fx = (p.homeX - p.x) * SPRING_K;
      let fy = (p.homeY - p.y) * SPRING_K;

      // Circular repulsors (logo)
      for (let r = 0; r < reps.length; r++) {
        const rep = reps[r];
        const dx = p.x - rep.x;
        const dy = p.y - rep.y;
        const distSq = dx * dx + dy * dy;
        const radius = rep.radius;
        const radiusSq = radius * radius;

        if (distSq < radiusSq && distSq > 0.01) {
          const dist = Math.sqrt(distSq);
          const strength = (rep.strength ?? 1) * REPULSOR_FORCE;
          const falloff = 1 - dist / radius;
          const force = falloff * falloff * strength;
          fx += (dx / dist) * force;
          fy += (dy / dist) * force;
        }
      }

      // Add velocity
      p.vx = (p.vx + fx) * DAMPING;
      p.vy = (p.vy + fy) * DAMPING;
      p.x += p.vx;
      p.y += p.vy;

      // Rectangular clear zones (text areas) — Hard clamp to prevent bouncing
      for (let z = 0; z < zones.length; z++) {
        const zone = zones[z];
        const pad = zone.padding ?? 30;
        const left = zone.x - pad;
        const right = zone.x + zone.width + pad;
        const top = zone.y - pad;
        const bottom = zone.y + zone.height + pad;

        if (p.x > left && p.x < right && p.y > top && p.y < bottom) {
          // Which edge is closest?
          const dLeft = p.x - left;
          const dRight = right - p.x;
          const dTop = p.y - top;
          const dBottom = bottom - p.y;
          const minDist = Math.min(dLeft, dRight, dTop, dBottom);

          // Pop particle to the edge and kill inward velocity
          if (minDist === dLeft) {
            p.x = left;
            if (p.vx > 0) p.vx *= -0.5; // slight bounce outward
          } else if (minDist === dRight) {
            p.x = right;
            if (p.vx < 0) p.vx *= -0.5;
          } else if (minDist === dTop) {
            p.y = top;
            if (p.vy > 0) p.vy *= -0.5;
          } else {
            p.y = bottom;
            if (p.vy < 0) p.vy *= -0.5;
          }
        }
      }
    }

    // ── Render ──
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];
      if (p.x < -20 || p.x > w + 20 || p.y < -20 || p.y > h + 20) continue;

      // Displacement feedback: displaced particles get slightly denser at zone edges
      const dx = p.x - p.homeX;
      const dy = p.y - p.homeY;
      const displacement = Math.sqrt(dx * dx + dy * dy);
      const displaceBoost = Math.min(displacement / 80, 1);
      const size = p.size + displaceBoost * 0.8;
      const opacity = p.opacity + displaceBoost * 0.06;

      ctx.globalAlpha = opacity;
      ctx.fillStyle = "#1a1a2e";
      ctx.beginPath();
      ctx.arc(p.x, p.y, size, 0, Math.PI * 2);
      ctx.fill();
    }

    animFrameRef.current = requestAnimationFrame(tick);
  }, [repulsorsRef, clearZonesRef]);

  const renderStatic = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const particles = particlesRef.current;
    const dpr = dprRef.current;
    const w = canvas.width / dpr;
    const h = canvas.height / dpr;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];
      if (p.homeX < -20 || p.homeX > w + 20 || p.homeY < -20 || p.homeY > h + 20) continue;

      ctx.globalAlpha = p.opacity;
      ctx.fillStyle = "#1a1a2e";
      ctx.beginPath();
      ctx.arc(p.homeX, p.homeY, p.size, 0, Math.PI * 2);
      ctx.fill();
    }
  }, []);

  useEffect(() => {
    initParticles();

    if (reducedMotion) {
      renderStatic();
    } else {
      animFrameRef.current = requestAnimationFrame(tick);
    }

    const onResize = () => {
      initParticles();
      if (reducedMotion) renderStatic();
    };
    window.addEventListener("resize", onResize);

    return () => {
      cancelAnimationFrame(animFrameRef.current);
      window.removeEventListener("resize", onResize);
    };
  }, [initParticles, tick, renderStatic, reducedMotion]);

  return (
    <canvas
      ref={canvasRef}
      className={className}
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none",
      }}
    />
  );
}

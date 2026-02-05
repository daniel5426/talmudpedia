"use client";

import React, { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";

interface AudioWaveformProps {
  className?: string;
  barCount?: number;
  color?: string;
  analyser?: AnalyserNode | null;
}

export function AudioWaveform({ 
  className, 
  barCount = 80,
  color = "currentColor",
  analyser
}: AudioWaveformProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<ReturnType<typeof requestAnimationFrame> | null>(null);
  const historyRef = useRef<number[]>([]);

  // Initialize history when barCount changes
  useEffect(() => {
    historyRef.current = new Array(barCount).fill(0);
  }, [barCount]);

  useEffect(() => {
    if (!analyser || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Handle high-DPI displays for better resolution
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    
    // Set actual size in memory (scaled to account for extra pixel density)
    // We use a fixed width based on bar count for now to ensure consistent look
    const width = barCount * 6; // 6px per bar (4px bar + 2px gap)
    canvas.width = width * dpr;
    canvas.height = 32 * dpr; // Fixed height of 32px
    
    // Normalize coordinate system to use css pixels.
    ctx.scale(dpr, dpr);
    
    // Style width/height
    canvas.style.width = `${width}px`;
    canvas.style.height = `32px`;

    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    let frameCount = 0;
    let maxVolInFrame = 0;

    const draw = () => {
      animationRef.current = requestAnimationFrame(draw);
      frameCount++;

      // Use Time Domain Data for waveform (amplitude over time)
      analyser.getByteTimeDomainData(dataArray);

      // Calculate RMS (Root Mean Square) for volume/amplitude of this frame
      let sum = 0;
      for(let i = 0; i < bufferLength; i++) {
          const x = dataArray[i] - 128; // Center at 0
          sum += x * x;
      }
      const rms = Math.sqrt(sum / bufferLength);
      
      // Normalize and amplify volume
      // Increased sensitivity: multiply by 8 instead of 3
      const volume = Math.min(1, (rms / 128) * 8);
      
      // Track max volume between updates to capture peaks
      if (volume > maxVolInFrame) {
          maxVolInFrame = volume;
      }

      // Update history only every 3 frames to slow down the movement
      if (frameCount % 6 === 0) {
          const history = historyRef.current;
          history.shift();
          history.push(maxVolInFrame);
          maxVolInFrame = 0; // Reset for next batch
      }

      ctx.clearRect(0, 0, width, 32);

      // Draw bars
      const totalBarWidth = width / barCount;
      const barWidth = totalBarWidth * 0.6; // 60% bar, 40% gap
      const gap = totalBarWidth * 0.4;

      if (color === "currentColor") {
          const style = getComputedStyle(canvas);
          ctx.fillStyle = style.color || "#000000";
      } else {
          ctx.fillStyle = color;
      }

      for (let i = 0; i < barCount; i++) {
        const value = historyRef.current[i];
        
        // Min height 2px, Max height 32px (canvas height)
        // We scale based on volume (0-1)
        const height = Math.max(2, value * 28); // Max height 28px (leaving 4px padding)
        
        const x = i * totalBarWidth + (gap / 2);
        const y = (32 - height) / 2; // Center vertically

        ctx.beginPath();
        const radius = Math.min(barWidth / 2, height / 2);
        if (ctx.roundRect) {
            ctx.roundRect(x, y, barWidth, height, radius);
        } else {
            ctx.fillRect(x, y, barWidth, height);
        }
        ctx.fill();
      }
    };

    draw();

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [analyser, barCount, color]);

  // Fallback for when no analyser is present (static or loading state)
  if (!analyser) {
     return (
        <div 
          className={cn(
            "flex items-center justify-center gap-1 h-8",
            className
          )}
          role="status"
          aria-label="Recording audio"
        >
          <style dangerouslySetInnerHTML={{__html: `
            @keyframes waveform-anim {
              0%, 100% { height: 4px; opacity: 0.5; }
              50% { height: 16px; opacity: 1; }
            }
          `}} />
          
          {Array.from({ length: 5 }).map((_, index) => (
            <div
              key={index}
              className="w-1 rounded-full bg-primary"
              style={{
                height: "4px",
                animation: `waveform-anim 1s ease-in-out infinite`,
                animationDelay: `${index * 0.1}s`,
                backgroundColor: color === "currentColor" ? undefined : color
              }}
            />
          ))}
        </div>
      );
  }

  return (
    <canvas 
        ref={canvasRef}
        className={cn("h-8", className)}
    />
  );
}

import { useEffect, useRef } from "react";

export function AudioWaveform({
  className,
  analyser,
  barCount = 24,
}: {
  className?: string;
  analyser?: AnalyserNode | null;
  barCount?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    const draw = () => {
      const width = canvas.width;
      const height = canvas.height;
      ctx.clearRect(0, 0, width, height);
      const bars = Math.max(6, barCount);
      for (let i = 0; i < bars; i += 1) {
        const x = (i / bars) * width;
        const sample = analyser ? 0.3 + Math.random() * 0.7 : 0.15 + Math.random() * 0.35;
        const barH = sample * height;
        ctx.fillStyle = "#2f67ff";
        ctx.fillRect(x, height - barH, Math.max(2, width / bars - 2), barH);
      }
      raf = requestAnimationFrame(draw);
    };

    draw();
    return () => cancelAnimationFrame(raf);
  }, [analyser, barCount]);

  return <canvas ref={canvasRef} className={className} width={420} height={40} />;
}

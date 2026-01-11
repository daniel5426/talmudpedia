"use client";

import Image from "next/image";
import { motion } from "framer-motion";
import { useEffect } from "react";
import { useTheme } from "next-themes";
import { palettes } from "@/lib/themes";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  const { setTheme } = useTheme();

  useEffect(() => {
    setTheme("light");
  }, [setTheme]);

  const oceanBreeze = palettes.find(p => p.id === 5);
  const authStyles = oceanBreeze ? {
    '--gradient-from': oceanBreeze.light['--gradient-from'],
    '--gradient-to': oceanBreeze.light['--gradient-to'],
    '--p-light-primary': oceanBreeze.light['--primary'],
    '--background': oceanBreeze.light['--background'],
    '--foreground': oceanBreeze.light['--foreground'],
    '--chat-background': oceanBreeze.light['--chat-background'],
    '--primary': oceanBreeze.light['--primary'],
    '--primary-foreground': oceanBreeze.light['--primary-foreground'],
    '--muted': oceanBreeze.light['--muted'],
    '--muted-foreground': oceanBreeze.light['--muted-foreground'],
    '--destructive': oceanBreeze.light['--destructive'],
    '--border': oceanBreeze.light['--border'],
    '--ring': oceanBreeze.light['--ring'],
    '--primary-soft': `color-mix(in oklch, ${oceanBreeze.light['--primary']} 5%, ${oceanBreeze.light['--background']})`,
  } as React.CSSProperties : {};

  return (
    <div className="relative min-h-svh flex flex-col items-center justify-center p-6 md:p-10 overflow-hidden bg-background" style={authStyles}>
      <div 
        className="fixed inset-0 z-[-1]"
        style={{
          background: `linear-gradient(to bottom right, ${oceanBreeze?.light['--gradient-from'] || '#dff2f4'}, ${oceanBreeze?.light['--gradient-to'] || '#1ca4ac'})`
        }}
      />

      {/* Decorative Animated Elements */}
      <div
        dir="ltr"
        className="fixed inset-0 pointer-events-none overflow-visible z-0"
      >
        {/* Large Faded Logo - Top Left */}
        <motion.div
          animate={{
            y: [0, -25, 0],
            rotate: [0, 8, 0],
            scale: [1, 1.05, 1],
          }}
          transition={{
            duration: 18,
            repeat: Infinity,
            ease: "easeInOut",
          }}
          className="absolute -left-[15%] -top-[10%] w-[min(100vw,800px)] opacity-[0.08]"
        >
          <Image
            src="/kesher.png"
            alt=""
            width={1800}
            height={1800}
            className="w-full h-auto"
            priority
          />
        </motion.div>

        {/* Medium White Logo - Bottom Right */}
        <motion.div
          animate={{
            y: [0, 40, 0],
            rotate: [0, -12, 0],
          }}
          transition={{
            duration: 22,
            repeat: Infinity,
            ease: "easeInOut",
          }}
          className="absolute -right-[8%] -bottom-[8%] w-[min(80vw,500px)] opacity-20 filter brightness-0 invert"
        >
          <Image
            src="/kesher.png"
            alt=""
            width={1800}
            height={1800}
            className="w-full h-auto"
            priority
          />
        </motion.div>

        {/* Small Teal Logo - Middle Right */}
        <motion.div
          animate={{
            scale: [1, 1.15, 1],
            x: [0, 30, 0],
            y: [0, 10, 0],
          }}
          transition={{
            duration: 14,
            repeat: Infinity,
            ease: "easeInOut",
          }}
          className="absolute right-[5%] top-[35%] w-[min(35vw,180px)] opacity-30 filter hue-rotate(160deg) saturate(140%)"
        >
          <Image
            src="/kesher.png"
            alt=""
            width={1800}
            height={1800}
            className="w-full h-auto"
          />
        </motion.div>

        {/* Tiny Blurred Logo - Middle Left */}
        <motion.div
          animate={{
            y: [0, 50, 0],
            x: [0, -20, 0],
            opacity: [0.1, 0.2, 0.1],
          }}
          transition={{
            duration: 10,
            repeat: Infinity,
            ease: "linear",
          }}
          className="absolute left-[20%] top-[20%] w-[80px] filter blur-sm brightness-0 invert"
        >
          <Image
            src="/kesher.png"
            alt=""
            width={500}
            height={500}
            className="w-full h-auto"
          />
        </motion.div>

        {/* Deep Sepia Logo - Bottom Left */}
        <motion.div
          animate={{
            rotate: [0, -5, 0],
            scale: [0.9, 1, 0.9],
          }}
          transition={{
            duration: 25,
            repeat: Infinity,
            ease: "easeInOut",
          }}
          className="absolute left-[10%] bottom-[15%] w-[min(30vw,250px)] opacity-15 filter sepia(100%) saturate(200%) hue-rotate(150deg)"
        >
          <Image
            src="/kesher.png"
            alt=""
            width={1000}
            height={1000}
            className="w-full h-auto"
          />
        </motion.div>

        {/* Rotating Subtle Logo - Center Right */}
        <motion.div
          animate={{
            rotate: 360,
          }}
          transition={{
            duration: 100,
            repeat: Infinity,
            ease: "linear",
          }}
          className="absolute right-[15%] bottom-[40%] w-[120px] opacity-[0.05] filter brightness-0"
        >
          <Image
            src="/kesher.png"
            alt=""
            width={500}
            height={500}
            className="w-full h-auto"
          />
        </motion.div>
      </div>

      <div className="relative z-10 w-full max-w-sm md:max-w-4xl">
        {children}
      </div>
    </div>
  );
}
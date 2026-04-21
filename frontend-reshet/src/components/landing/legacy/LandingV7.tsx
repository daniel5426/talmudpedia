"use client";

import Link from "next/link";
import { ChevronDown, Search, Mic, Home, CheckCircle2, Users, BarChart, LayoutGrid, PauseCircle, ShieldAlert } from "lucide-react";

export function LandingV7() {
  return (
    <div className="min-h-screen bg-[#050505] text-white font-sans overflow-x-hidden selection:bg-white/20 selection:text-white">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,300;6..72,400;6..72,500;6..72,600&family=Inter:wght@300;400;500;600&display=swap');
        .font-obsidian { font-family: 'Newsreader', serif; }
        .font-sans-inter { font-family: 'Inter', sans-serif; }
      `}</style>
      
      {/* Navbar */}
      <nav className="fixed top-0 z-50 w-full bg-[#050505]/95 backdrop-blur-md border-b border-white/[0.04] h-[72px] flex items-center">
        <div className="w-full max-w-[1400px] mx-auto px-6 flex items-center justify-between font-sans-inter">
          <Link href="/" className="flex items-center gap-2">
            <div className="w-[26px] h-[26px] rounded-full border-[1.5px] border-white flex items-center justify-center relative overflow-hidden shrink-0">
               <div className="absolute w-[36px] h-[1px] bg-white rotate-45" />
               <div className="absolute w-[36px] h-[1px] bg-white -rotate-45" />
               <div className="w-[12px] h-[12px] bg-[#050505] rounded-full border-[1.5px] border-white z-10" />
            </div>
            <span className="font-obsidian text-[22px] tracking-tight text-white mb-0.5">obsidian</span>
          </Link>

          <div className="hidden md:flex items-center gap-8 text-[13px] font-medium text-white/50">
            <button className="flex items-center gap-1.5 hover:text-white transition-colors">
              What we offer <ChevronDown className="w-[12px] h-[12px] opacity-70" />
            </button>
            <button className="flex items-center gap-1.5 hover:text-white transition-colors">
              Who's it for <ChevronDown className="w-[12px] h-[12px] opacity-70" />
            </button>
            <Link href="#" className="hover:text-white transition-colors">Pricing</Link>
            <Link href="#" className="hover:text-white transition-colors">About</Link>
          </div>

          <div className="flex items-center">
            <Link href="/auth/login" className="px-5 py-2.5 bg-white/10 hover:bg-white/15 text-white text-[13px] font-medium rounded-full transition-colors border border-white/5">
              Get started
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative pt-[180px] pb-32 px-6 flex flex-col items-center text-center overflow-hidden min-h-[90vh]">
         {/* Subtle background glow */}
         <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-white/[0.03] blur-[150px] rounded-full pointer-events-none" />
         
         <div className="relative z-20 max-w-4xl mx-auto flex flex-col items-center">
           <h1 className="font-obsidian text-[56px] md:text-[88px] leading-[1.05] tracking-[-0.03em] font-light text-[#f5f5f5]">
             The all-in-one platform <br/> for financial advisers
           </h1>
           <p className="mt-8 text-[15px] md:text-[17px] text-white/60 max-w-2xl leading-relaxed font-sans-inter font-light">
             AI-powered practice management available now - with <br className="hidden md:block"/> integrated custody and execution launching soon.
           </p>
           
           <Link href="/auth/login" className="mt-10 px-6 py-3.5 bg-white text-black hover:bg-white/90 text-[14px] font-medium rounded-full transition-colors font-sans-inter shadow-[0_0_30px_rgba(255,255,255,0.15)]">
             Get Started For Free
           </Link>
         </div>

         {/* Dashboard Mockup overlaying large dark abstract shapes */}
         <div className="relative w-full max-w-[1200px] mx-auto mt-28 z-20">
            {/* Dark abstract bg rocks simulating the obsidian aesthetic in CSS */}
            <div className="absolute -left-[15%] top-[10%] w-[40%] h-[150%] bg-[#1a1a1a] rounded-full blur-2xl opacity-20 -rotate-12" />
            <div className="absolute -right-[15%] top-[20%] w-[35%] h-[120%] bg-[#222] rounded-full blur-2xl opacity-20 rotate-45" />
            
            <div className="relative rounded-[24px] border border-white/10 bg-[#161616]/70 backdrop-blur-2xl shadow-2xl p-4 md:p-6 overflow-hidden min-h-[400px] flex">
               
               {/* Left Sidebar */}
               <div className="w-[80px] border-r border-white/5 flex flex-col items-center py-4 gap-8 hidden md:flex shrink-0">
                  <div className="w-10 h-10 rounded-full bg-gradient-to-br from-[#ff5a00] to-[#5a00ff] opacity-80" />
                  <div className="flex flex-col gap-6 text-white/40">
                    <div className="flex flex-col items-center gap-1.5 hover:text-white cursor-pointer transition">
                      <Home className="w-5 h-5" />
                      <span className="text-[10px]">Home</span>
                    </div>
                    <div className="flex flex-col items-center gap-1.5 hover:text-white cursor-pointer transition">
                      <CheckCircle2 className="w-5 h-5" />
                      <span className="text-[10px]">Tasks</span>
                    </div>
                    <div className="flex flex-col items-center gap-1.5 hover:text-white cursor-pointer transition">
                      <Home className="w-5 h-5" />
                      <span className="text-[10px]">Households</span>
                    </div>
                    <div className="flex flex-col items-center gap-1.5 hover:text-white cursor-pointer transition">
                      <Users className="w-5 h-5" />
                      <span className="text-[10px]">People</span>
                    </div>
                    <div className="flex flex-col items-center gap-1.5 hover:text-white cursor-pointer transition">
                      <BarChart className="w-5 h-5" />
                      <span className="text-[10px]">Assets</span>
                    </div>
                    <div className="flex flex-col items-center gap-1.5 hover:text-white cursor-pointer transition">
                      <LayoutGrid className="w-5 h-5" />
                      <span className="text-[10px]">Apps</span>
                    </div>
                  </div>
               </div>

               {/* Main Panel */}
               <div className="flex-1 p-4 md:pl-10 pb-10">
                  <div className="flex flex-col md:flex-row md:items-center justify-between mb-10 gap-4">
                     <div className="flex items-center gap-4">
                       <h2 className="text-[22px] font-medium text-white">Day plan</h2>
                       <div className="flex items-center gap-2 text-[13px] text-white/40">
                          <span className="opacity-50">←</span> Mon, 22 Sept 2025 <span className="opacity-50">→</span>
                       </div>
                     </div>
                     <div className="relative w-full md:w-[280px]">
                       <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
                       <input type="text" placeholder="Search anything" className="w-full bg-white/5 border border-white/5 rounded-full pl-10 pr-12 py-2 text-[13px] text-white placeholder:text-white/30 outline-none focus:border-white/20 transition-colors" />
                       <div className="absolute right-3 top-1/2 -translate-y-1/2 flex gap-1">
                          <kbd className="px-1.5 py-0.5 bg-white/10 rounded text-[10px] text-white/50">⌘</kbd>
                          <kbd className="px-1.5 py-0.5 bg-white/10 rounded text-[10px] text-white/50">K</kbd>
                       </div>
                     </div>
                  </div>

                  <div className="grid md:grid-cols-3 gap-6">
                     <div className="space-y-4">
                        <div className="flex items-center justify-between">
                          <h3 className="text-[14px] text-white/70 font-medium">Meetings</h3>
                          <button className="flex items-center gap-2 bg-white/10 hover:bg-white/15 border border-white/5 px-3 py-1.5 rounded-full text-[12px] transition-colors"><Mic className="w-3.5 h-3.5"/> New meeting</button>
                        </div>
                        <div className="bg-white/5 border border-white/5 rounded-[16px] p-5 hover:bg-white/[0.07] transition-colors cursor-pointer">
                           <div className="flex items-center justify-between text-[12px] text-white/40 mb-3">
                             <span>10:00 - 10:40 · Zoom</span>
                             <div className="flex -space-x-1.5">
                                <div className="w-5 h-5 rounded-full border border-[#222] bg-[#444] shrink-0"><img src="https://api.dicebear.com/7.x/notionists/svg?seed=melissa" className="w-full rounded-full"/></div>
                                <div className="w-5 h-5 rounded-full border border-[#222] bg-[#ff8a00] shrink-0" />
                             </div>
                           </div>
                           <div className="text-[15px] font-medium text-white">Melissa Moore Q3 financial review</div>
                        </div>
                        <div className="bg-white/5 border border-white/5 rounded-[16px] p-5 hover:bg-white/[0.07] transition-colors cursor-pointer">
                           <div className="flex items-center justify-between text-[12px] text-white/40 mb-3">
                             <span>11:00 - 11:45 · In person</span>
                             <div className="w-5 h-5 rounded-full border border-[#222] bg-[#111] shrink-0 text-[10px] flex items-center justify-center font-bold">NP</div>
                           </div>
                           <div className="text-[15px] font-medium text-white/40">Introduction call with Nicole Perez</div>
                        </div>
                     </div>

                     <div className="space-y-4">
                        <div className="flex items-center justify-between">
                          <h3 className="text-[14px] text-white/70 font-medium">Post meeting</h3>
                        </div>
                        <div className="bg-white/5 border border-white/5 rounded-[16px] p-5 hover:bg-white/[0.07] transition-colors cursor-pointer">
                           <div className="text-[12px] text-white/40 mb-3">08:15 - 08:40 · In person</div>
                           <div className="text-[15px] font-medium text-white/50">Cynthia Davis Q3 financial review</div>
                        </div>
                        <div className="bg-white/5 border border-white/5 rounded-[16px] p-5 hover:bg-white/[0.07] transition-colors cursor-pointer">
                           <div className="flex items-center justify-between text-[12px] text-white/40 mb-3">
                             <span>09:00 - 09:40 · In person</span>
                             <div className="flex -space-x-1.5">
                                <div className="w-5 h-5 rounded-full border border-[#222] bg-[#444] shrink-0"><img src="https://api.dicebear.com/7.x/notionists/svg?seed=1" className="w-full rounded-full"/></div>
                                <div className="w-5 h-5 rounded-full border border-[#222] bg-[#666] shrink-0"><img src="https://api.dicebear.com/7.x/notionists/svg?seed=2" className="w-full rounded-full"/></div>
                                <div className="w-5 h-5 rounded-full border border-[#222] bg-[#222] shrink-0 text-[9px] flex items-center justify-center">+2</div>
                             </div>
                           </div>
                           <div className="text-[15px] font-medium text-white/50">Gift for new household member</div>
                        </div>
                     </div>

                     <div className="space-y-4">
                        <div className="flex items-center justify-between">
                          <h3 className="text-[14px] text-white/70 font-medium">Tasks for today</h3>
                          <button className="flex items-center gap-2 bg-white/10 hover:bg-white/15 border border-white/5 px-3 py-1.5 rounded-full text-[12px] transition-colors">
                            <span className="text-[16px] leading-[0] mb-[2px]">+</span> Add task
                          </button>
                        </div>
                        <div className="bg-white/5 border border-white/5 rounded-[16px] p-5 hover:bg-white/[0.07] transition-colors cursor-pointer flex flex-col justify-between">
                           <div className="flex items-center justify-between text-[12px] text-white/40 mb-4">
                             <div className="flex items-center gap-1.5"><CheckCircle2 className="w-3.5 h-3.5"/> 10:00 · Today</div>
                             <div className="px-2 py-0.5 rounded text-[#eb814b] border border-[#eb814b]/20 bg-[#eb814b]/10 text-[11px] flex items-center gap-1">Review <ChevronDown className="w-3 h-3"/></div>
                           </div>
                           <div className="text-[15px] font-medium text-white/70 leading-snug">Go over Patel Household Trust documents.</div>
                        </div>
                        <div className="bg-white/5 border border-white/5 rounded-[16px] p-5 hover:bg-white/[0.07] transition-colors cursor-pointer flex flex-col justify-between">
                           <div className="flex items-center justify-between text-[12px] text-white/40 mb-4">
                             <div className="flex items-center gap-1.5"><CheckCircle2 className="w-3.5 h-3.5"/> 10:00 · Today</div>
                             <div className="px-2 py-0.5 rounded text-[#eb814b] border border-[#eb814b]/20 bg-[#eb814b]/10 text-[11px] flex items-center gap-1">Review <ChevronDown className="w-3 h-3"/></div>
                           </div>
                           <div className="text-[15px] font-medium text-white/40 leading-snug">Investment plan for Richard Collins</div>
                        </div>
                     </div>
                  </div>
               </div>
            </div>
         </div>
      </section>

      {/* Feature Section 1: Two large cards */}
      <section className="px-6 py-24 max-w-[1240px] mx-auto">
        <h2 className="font-obsidian text-[40px] md:text-[52px] leading-[1.1] mb-12 text-[#f5f5f5] font-light tracking-[-0.02em]">
          Save Time & Grow AUM
        </h2>
        <div className="grid md:grid-cols-2 gap-6 relative">
          
          {/* Left Feature Card */}
          <div className="bg-[#0f0f0f] border border-white/5 rounded-3xl overflow-hidden aspect-[4/3] relative group group-hover:border-white/10 transition-colors">
            {/* Dark abstract orb */}
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-[80%] h-[80%] rounded-full bg-gradient-to-tr from-[#ff3c00]/40 to-[#ffaa00]/20 blur-3xl opacity-60" />
            </div>
            
            {/* Mock Floating UI recording */}
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[80%] max-w-[340px] bg-white/10 backdrop-blur-2xl border border-white/10 rounded-2xl p-5 shadow-2xl">
              <div className="flex items-center justify-between mb-4">
                <span className="text-[14px] text-white/80 font-medium">02:04 Recording meeting</span>
                <div className="flex items-center gap-1 text-[12px] bg-white text-black px-2.5 py-1 rounded-full font-medium">
                  <PauseCircle className="w-3.5 h-3.5 fill-current"/> Stop
                </div>
              </div>
              <div className="flex items-center gap-1 h-8 px-2 justify-between opacity-80">
                 {[4,8,12,6,16,10,20,5,15,8,12,6,10,4,8,18,6].map((h, i) => (
                   <div key={i} className="w-[1.5px] bg-white rounded-full transition-all duration-500 ease-in-out" style={{height: `${h}px`, opacity: 1 - (i*0.03)}} />
                 ))}
              </div>
            </div>

            <div className="absolute bottom-6 left-6 text-white font-sans-inter">
              <p className="text-[#3fdca3] text-[11px] mb-2 font-medium">Free</p>
              <h3 className="font-obsidian text-[28px] font-light">AI Practice Management</h3>
            </div>
          </div>

          {/* Right Feature Card */}
          <div className="bg-[#0f0f0f] border border-white/5 rounded-3xl overflow-hidden aspect-[4/3] relative group hover:border-white/10 transition-colors">
             {/* Subtle rock texture background placeholder using noise and gradients */}
             <div className="absolute inset-0 bg-[#141414]" />
             <div className="absolute top-[-10%] right-[-10%] w-[60%] h-[60%] bg-[#3fdca3]/10 blur-3xl rounded-full" />
             
             {/* Mock Floating UI trade info */}
             <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[85%] max-w-[360px] bg-[#1a1a1a]/95 backdrop-blur-3xl border border-white/5 rounded-2xl p-6 shadow-2xl">
               <div className="flex items-center justify-between text-[12px] text-white/50 mb-1">
                 <span>Return by fund</span>
                 <span>Closed: Jan 7, 08:11 EST</span>
               </div>
               <div className="text-[28px] text-white font-medium mb-6">18.5%</div>
               
               {/* Mock Graph */}
               <svg viewBox="0 0 300 60" className="w-full h-12 stroke-[#3fdca3] fill-none stroke-[2] mb-8" preserveAspectRatio="none">
                 <path d="M0 40 Q 20 50 40 30 T 80 40 T 130 20 T 180 30 T 220 10 T 260 20 L 300 0"/>
               </svg>

               <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-6 gap-y-3 text-[12px] border-t border-white/5 pt-4">
                 <div className="text-white/50 mb-1">Positions</div>
                 <div className="text-white/50 text-right mb-1">Current</div>
                 <div className="text-white/50 text-right mb-1">Target</div>
                 <div className="text-white/50 text-right mb-1">Trade size</div>
                 
                 <div className="text-white">SPX</div>
                 <div className="text-white/60 text-right">45.0%</div>
                 <div className="text-white/30 text-right bg-white/5 rounded px-2">50.0%</div>
                 <div className="text-[#3fdca3] text-right font-medium">+5%</div>
                 
                 <div className="text-white">Nasdaq 100</div>
                 <div className="text-white/60 text-right">35.0%</div>
                 <div className="text-white/30 text-right bg-white/5 rounded px-2">50.0%</div>
                 <div className="text-[#3fdca3] text-right font-medium">+5%</div>
                 
                 <div className="text-white">DAX</div>
                 <div className="text-white/60 text-right">20.0%</div>
                 <div className="text-white/30 text-right bg-white/5 rounded px-2">50.0%</div>
                 <div className="text-[#ff5a00] text-right font-medium">-15%</div>
               </div>
             </div>

             <div className="absolute bottom-6 left-6 text-white font-sans-inter">
              <p className="text-white/40 text-[11px] mb-2 font-medium">Coming Soon</p>
              <h3 className="font-obsidian text-[28px] font-light">Execution & Custody</h3>
            </div>
          </div>
        </div>
      </section>

      {/* Split Section 1 */}
      <section className="px-6 py-24 max-w-[1240px] mx-auto border-t border-white/5">
        <h2 className="font-obsidian text-[44px] md:text-[56px] leading-[1.1] mb-20 text-[#f5f5f5] font-light tracking-[-0.02em]">
          The platform that <br/> scales your firm
        </h2>
        
        <div className="grid md:grid-cols-[1fr_1.2fr] gap-16 md:gap-24">
           <div className="flex flex-col">
              <h3 className="font-obsidian text-[32px] font-light mb-4">Independent firms</h3>
              <p className="text-white/50 text-[15px] leading-relaxed max-w-sm mb-12">
                Spend less time on admin and more time delivering advice that matters.
              </p>
              
              <div className="space-y-0.5">
                 {["Day plan", "AI search", "AI meeting summaries"].map(item => (
                   <div key={item} className="border-b border-white/[0.06] py-5">
                     <span className="text-white/40 text-[15px]">{item}</span>
                   </div>
                 ))}
                 <div className="border-b border-white/[0.2] py-5 relative">
                   <span className="text-white text-[15px]">Document digitisation</span>
                   <div className="absolute bottom-[-1px] left-0 w-24 h-[2px] bg-white" />
                 </div>
                 <div className="py-5">
                   <span className="text-white/40 text-[15px]">Suitability report</span>
                 </div>
              </div>
           </div>

           <div className="bg-[#111] rounded-[32px] border border-white/5 relative overflow-hidden min-h-[500px] flex items-center justify-center">
              <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent opacity-20" />
              
              {/* Mock Floating UI recommendation */}
              <div className="relative w-[340px] bg-[#222]/90 backdrop-blur-xl border border-white/10 rounded-2xl overflow-hidden shadow-2xl">
                 <div className="p-5 flex items-center justify-between border-b border-white/5">
                   <div className="flex items-center gap-3">
                     <div className="w-8 h-8 rounded-full border border-white/10 bg-black overflow-hidden">
                       <img src="https://api.dicebear.com/7.x/notionists/svg?seed=chloe" className="w-full" />
                     </div>
                     <span className="text-[14px] font-medium text-white/90">Chloe Lee</span>
                   </div>
                   <span className="text-[12px] text-white/40">Suitability report</span>
                 </div>
                 <div className="p-5 space-y-5">
                    <div>
                      <h4 className="text-[13px] text-white/50 mb-1.5">Recommendation</h4>
                      <p className="text-[13px] text-white/80 leading-relaxed font-light">
                        Your plan is designed for long-term wealth building, with flexible access.
                      </p>
                    </div>

                    <div className="space-y-4 pt-2">
                       <div className="flex items-start gap-4">
                         <div className="w-8 h-8 rounded-full bg-white/5 flex items-center justify-center shrink-0 border border-white/5 border-t-white/10"><div className="w-3 h-3 rounded-full border border-[#ff5a00] flex items-center justify-center"><div className="w-1 h-1 bg-[#ff5a00] border rounded-full"/></div></div>
                         <div className="flex-1 border-b border-white/5 pb-4 flex justify-between items-center group cursor-pointer hover:border-white/20 transition-colors">
                           <div>
                             <div className="text-[12px] text-white/50 mb-0.5">Goals</div>
                             <div className="text-[14px] text-white font-medium">Retirement · +10 years</div>
                           </div>
                           <ChevronDown className="w-4 h-4 text-white/20 group-hover:text-white/50 transition-colors" />
                         </div>
                       </div>

                       <div className="flex items-start gap-4">
                         <div className="w-8 h-8 rounded-full bg-white/5 flex items-center justify-center shrink-0 border border-white/5 border-t-white/10"><BarChart className="w-3.5 h-3.5 text-[#eb814b]" /></div>
                         <div className="flex-1 border-b border-white/5 pb-4 flex justify-between items-center group cursor-pointer hover:border-white/20 transition-colors">
                           <div>
                             <div className="text-[12px] text-white/50 mb-0.5">Account</div>
                             <div className="text-[14px] text-white font-medium">GIA, ISA</div>
                           </div>
                           <ChevronDown className="w-4 h-4 text-white/20 group-hover:text-white/50 transition-colors" />
                         </div>
                       </div>
                       
                       <div className="flex items-start gap-4">
                         <div className="w-8 h-8 rounded-full bg-white/5 flex items-center justify-center shrink-0 border border-white/5 border-t-white/10"><ShieldAlert className="w-3.5 h-3.5 text-[#ff5a00]" /></div>
                         <div className="flex-1 flex justify-between items-center group cursor-pointer transition-colors pb-1">
                           <div>
                             <div className="text-[12px] text-white/50 mb-0.5">Risk</div>
                             <div className="text-[14px] text-white font-medium">Growth / comfortable with volatility</div>
                           </div>
                           <ChevronDown className="w-4 h-4 text-white/20 group-hover:text-white/50 transition-colors -rotate-90" />
                         </div>
                       </div>
                    </div>
                 </div>
              </div>
           </div>
        </div>
      </section>

      {/* Split Section 2 */}
      <section className="px-6 py-24 max-w-[1240px] mx-auto border-t border-white/5">
        <h2 className="font-obsidian text-[44px] md:text-[56px] leading-[1.1] mb-20 text-[#f5f5f5] font-light tracking-[-0.02em]">
          Unlock rapid growth
        </h2>
        
        <div className="grid md:grid-cols-[1.2fr_1fr] gap-16 md:gap-24 items-center">
           
           <div className="bg-[#111] rounded-[32px] border border-white/5 relative overflow-hidden min-h-[500px] flex items-center justify-center order-2 md:order-1">
              <div className="absolute inset-0 bg-gradient-to-tr from-[#3a2015]/40 to-transparent opacity-50 blur-3xl" />
              
              {/* Mock Floating UI audit trails */}
              <div className="relative w-[80%] max-w-[420px] bg-[#222]/90 backdrop-blur-xl border border-white/10 rounded-2xl overflow-hidden shadow-2xl p-6">
                 <div className="text-[13px] text-white/50 mb-6 font-medium">Audit trials</div>
                 
                 <div className="grid grid-cols-[auto_1fr_auto] gap-x-6 gap-y-5 text-[13px]">
                   <div className="text-white/50 mb-2">Time</div>
                   <div className="text-white/50 mb-2">Event</div>
                   <div className="text-white/50 mb-2 text-right">Outcome</div>
                   
                   <div className="text-white/60">10:14</div>
                   <div className="text-white">Policy update (Alpha Capital)</div>
                   <div className="text-white font-medium text-right">Applied</div>
                   
                   <div className="text-white/60">10:16</div>
                   <div className="text-white">Report export (Silvergate)</div>
                   <div className="text-[#3fdca3] font-medium text-right">Completed</div>
                   
                   <div className="text-white/60">10:18</div>
                   <div className="text-white">Cross-organization request (Crescent → Silvergate)</div>
                   <div className="text-white/40 font-medium text-right">Denied</div>
                   
                   <div className="text-white/60">10:22</div>
                   <div className="text-white">User access review (Alpha Capital)</div>
                   <div className="text-white font-medium text-right">Logged</div>
                 </div>
              </div>
           </div>

           <div className="flex flex-col order-1 md:order-2">
              <h3 className="font-obsidian text-[32px] font-light mb-4">Consolidators</h3>
              <p className="text-white/50 text-[15px] leading-relaxed max-w-sm mb-12">
                Unify firms, data, and controls to scale faster – without operational drag.
              </p>
              
              <div className="space-y-0.5">
                 {["Multi-firm oversight", "Rapid onboarding", "Document digitisation", "Data segregation", "Role-based access"].map(item => (
                   <div key={item} className="border-b border-white/[0.06] py-5">
                     <span className="text-white/40 text-[15px]">{item}</span>
                   </div>
                 ))}
                 <div className="border-b border-white/[0.2] py-5 relative mt-4">
                   <div className="absolute top-[-1px] left-0 w-24 h-[2px] bg-white" />
                   <span className="text-white text-[15px]">Audit trails</span>
                 </div>
              </div>
           </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="mt-20 border-t border-white/[0.05] pt-16 pb-10 px-6 max-w-[1300px] mx-auto">
         <div className="flex flex-col lg:flex-row justify-between gap-12 text-[12px] text-white/40 font-sans-inter">
            <div className="max-w-[400px]">
               <p className="mb-4 leading-relaxed hover:text-white/60 transition-colors">
                 Obsidian Securities Limited is not yet authorised by the Financial Conduct Authority.<br/>
                 Prior to becoming authorised no information regarding the future provision of custody and execution services is intended as an invitation or inducement to apply for these services, nor does it constitute financial advice.
               </p>
               <div className="flex items-center gap-2 mt-auto pt-6 border-t border-white/[0.05] w-full">
                  <span>Powered by</span>
                  <div className="flex items-center gap-1.5 text-white/50 font-obsidian text-[16px] tracking-tight">
                    <div className="w-5 h-5 rounded-full border border-current flex items-center justify-center relative overflow-hidden">
                       <div className="absolute w-[20px] h-[1px] bg-current rotate-45" />
                       <div className="absolute w-[20px] h-[1px] bg-current -rotate-45" />
                       <div className="w-[8px] h-[8px] bg-[#050505] rounded-full border border-current z-10" />
                    </div>
                    RockCore
                  </div>
               </div>
            </div>
            
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-12 lg:gap-20">
               <div className="col-span-2">
                 <div className="flex items-center gap-2 text-white mb-6">
                    <div className="w-[22px] h-[22px] rounded-full border-[1.5px] border-white flex items-center justify-center relative overflow-hidden shrink-0">
                       <div className="absolute w-[30px] h-[1px] bg-white rotate-45" />
                       <div className="absolute w-[30px] h-[1px] bg-white -rotate-45" />
                       <div className="w-[10px] h-[10px] bg-[#050505] rounded-full border-[1.5px] border-white z-10" />
                    </div>
                    <span className="font-obsidian text-[18px] tracking-tight">obsidian</span>
                 </div>
                 <p className="leading-relaxed hover:text-white/60 transition-colors">
                   Obsidian Technologies Limited is a company registered in England & Wales with company number 16326982. Our office is located at 30 Churchill Place, Canary Wharf, London, England, E14 5RE.
                 </p>
                 <div className="flex items-center gap-4 mt-8">
                   <div className="w-12 h-12 rounded-full border border-white/10 flex items-center justify-center relative bg-white/5 text-[8px] tracking-[0.2em] font-medium text-white/50">
                      <div className="absolute inset-1 rounded-full border border-white/10 border-dashed animate-spin-slow"></div>
                      GDPR
                   </div>
                   <div className="w-12 h-12 rounded-full border border-white/10 flex items-center justify-center bg-white/5">
                      <ShieldAlert className="w-4 h-4 text-white/50" />
                   </div>
                 </div>
               </div>

               <div>
                 <h4 className="text-white/30 font-medium mb-6">Product</h4>
                 <ul className="space-y-4">
                   <li><Link href="#" className="text-white/70 hover:text-white transition-colors">AI Practice Management</Link></li>
                   <li><Link href="#" className="text-white/70 hover:text-white transition-colors">Execution & Custody</Link></li>
                 </ul>
               </div>

               <div>
                 <h4 className="text-white/30 font-medium mb-6">Obsidian</h4>
                 <ul className="space-y-4">
                   <li><Link href="#" className="text-white/70 hover:text-white transition-colors">Resources</Link></li>
                   <li><Link href="#" className="text-white/70 hover:text-white transition-colors">About Us</Link></li>
                   <li><Link href="#" className="text-white/70 hover:text-white transition-colors">Careers</Link></li>
                   <li><Link href="#" className="text-white/70 hover:text-white transition-colors">Contact Us</Link></li>
                   <li><Link href="#" className="text-white/70 hover:text-white transition-colors">Linkedin</Link></li>
                 </ul>
               </div>

               <div className="col-span-2 lg:col-span-4 mt-12 pt-8 border-t border-white/[0.05] flex flex-col md:flex-row justify-between items-center gap-4">
                 <span>© 2026 Obsidian Technologies Limited. Obsidian is the registered trademark of Obsidian Technologies Limited.</span>
                 <div className="flex items-center gap-6">
                   <Link href="#" className="text-white/70 hover:text-white transition-colors">Privacy Policy</Link>
                   <Link href="#" className="text-white/70 hover:text-white transition-colors">Terms of Service</Link>
                   <Link href="#" className="text-white/70 hover:text-white transition-colors">Cookie Policy</Link>
                 </div>
               </div>
            </div>
         </div>

         {/* Giant watermark */}
         <div className="mt-16 sm:mt-24 pointer-events-none select-none flex justify-center overflow-hidden">
            <span className="font-obsidian text-[15vw] leading-[0.7] tracking-[-0.03em] text-[#111] font-light">
              obsidian
            </span>
         </div>
      </footer>
    </div>
  );
}

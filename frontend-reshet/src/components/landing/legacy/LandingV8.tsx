"use client";

import Link from "next/link";
import { ChevronDown, Network, Database, LayoutPanelTop, Play, Zap, Shield, Search, ArrowRight, Activity, Code2, Link as LinkIcon, Lock, User, CheckCircle2 } from "lucide-react";

export function LandingV8() {
  return (
    <div className="min-h-screen bg-[#020202] text-white font-sans overflow-x-hidden selection:bg-white/20 selection:text-white pb-32">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,300;6..72,400;6..72,500&family=Inter:wght@300;400;500;600&display=swap');
        .font-serif-display { font-family: 'Newsreader', serif; }
        .font-sans-ui { font-family: 'Inter', sans-serif; }
      `}</style>

      {/* Navbar: Blends Obsidian's dark minimalism with Dub's structured layout */}
      <nav className="fixed top-0 z-50 w-full bg-[#020202]/80 backdrop-blur-xl border-b border-white/[0.04] h-16 flex items-center">
        <div className="w-full max-w-[1240px] mx-auto px-6 flex items-center justify-between font-sans-ui">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="w-6 h-6 bg-white text-black font-serif-display font-medium text-[15px] flex items-center justify-center rounded-sm">
              T
            </div>
            <span className="font-medium text-[15px] tracking-tight text-white/90">Talmudpedia</span>
          </Link>

          <div className="hidden md:flex items-center gap-8 text-[13px] font-medium text-white/50">
            <button className="flex items-center gap-1.5 hover:text-white transition-colors">
              Platform <ChevronDown className="w-3.5 h-3.5 opacity-70" />
            </button>
            <Link href="#" className="hover:text-white transition-colors">Solutions</Link>
            <Link href="#" className="hover:text-white transition-colors">Customers</Link>
            <Link href="#" className="hover:text-white transition-colors">Docs</Link>
          </div>

          <div className="flex items-center gap-3">
            <Link href="/auth/login" className="hidden sm:block text-[13px] font-medium text-white/70 hover:text-white transition-colors px-3 py-2">
              Sign in
            </Link>
            <Link href="/auth/login" className="px-4 py-2 bg-white text-black hover:bg-gray-100 text-[13px] font-medium rounded-full transition-colors shadow-[0_0_20px_rgba(255,255,255,0.1)]">
              Start building
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section: Epic dark canvas (Obsidian) structured with grid & precise typography (Dub) */}
      <section className="relative pt-[160px] pb-32 px-6 flex flex-col items-center text-center overflow-hidden min-h-[85vh]">
         {/* Deep layered glows */}
         <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[500px] bg-white/[0.03] blur-[120px] rounded-full pointer-events-none" />
         <div className="absolute top-[20%] left-1/2 -translate-x-1/2 w-[400px] h-[300px] bg-[#3fdca3]/[0.05] blur-[100px] rounded-full pointer-events-none" />

         {/* Precision grid (Dub style) but dark */}
         <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff05_1px,transparent_1px),linear-gradient(to_bottom,#ffffff05_1px,transparent_1px)] bg-[size:64px_64px] [mask-image:radial-gradient(ellipse_80%_80%_at_50%_10%,black_20%,transparent_100%)]" />

         <div className="relative z-20 w-full max-w-[1000px] mx-auto flex flex-col items-center">
           <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-white/10 bg-white/[0.03] backdrop-blur-md mb-8">
             <span className="flex h-2 w-2 rounded-full bg-[#3fdca3] animate-pulse"></span>
             <span className="text-[12px] font-medium tracking-wide text-white/70 font-sans-ui uppercase">Enterprise AI Infrastructure</span>
           </div>

           <h1 className="font-serif-display text-[52px] md:text-[80px] leading-[0.95] tracking-[-0.03em] font-light text-white mb-6">
             Operate AI agents <br/>
             <span className="text-white/60">at production scale.</span>
           </h1>
           
           <p className="text-[17px] md:text-[19px] text-white/50 max-w-2xl leading-relaxed font-sans-ui font-light mb-10">
             Talmudpedia unifies agent reasoning graphs, knowledge pipelines, and runtime governance into a single, deployable operating surface.
           </p>

           <div className="flex flex-col sm:flex-row items-center gap-4 w-full justify-center">
             <Link href="/auth/login" className="w-full sm:w-auto px-7 py-3.5 bg-white text-black hover:bg-gray-100 text-[14px] font-medium rounded-full transition-colors flex items-center justify-center gap-2 group shadow-[0_0_30px_rgba(255,255,255,0.15)]">
               Deploy your first agent <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
             </Link>
             <Link href="/admin/apps" className="w-full sm:w-auto px-7 py-3.5 bg-white/5 border border-white/10 hover:bg-white/10 text-white text-[14px] font-medium rounded-full transition-colors flex items-center justify-center backdrop-blur-md">
               Read the docs
             </Link>
           </div>
         </div>

         {/* Hero Dashboard Mockup - Blending Dub's precision with Obsidian's glassmorphism */}
         <div className="relative w-full max-w-[1100px] mx-auto mt-24 z-20">
            <div className="absolute inset-0 bg-gradient-to-t from-[#020202] via-transparent to-transparent z-30 pointer-events-none translate-y-12" />
            
            <div className="rounded-t-[24px] border border-white/10 border-b-0 bg-[#0a0a0a]/80 backdrop-blur-2xl shadow-2xl p-2 pb-0 overflow-hidden flex flex-col md:flex-row min-h-[450px]">
               
               {/* Sidebar (Dub structural feel) */}
               <div className="w-[240px] p-4 hidden md:flex flex-col border-r border-white/5">
                 <div className="text-[11px] font-semibold text-white/30 uppercase tracking-[0.15em] mb-4 pl-2">Runtime</div>
                 <div className="flex items-center gap-2.5 px-3 py-2 bg-white/5 rounded-xl text-white text-[13px] font-medium mb-1 border border-white/5">
                   <Activity className="w-4 h-4 text-[#3fdca3]" /> Active Traces
                 </div>
                 <div className="flex items-center gap-2.5 px-3 py-2 hover:bg-white/5 rounded-xl text-white/50 hover:text-white/80 text-[13px] font-medium mb-1 transition-colors">
                   <Database className="w-4 h-4" /> Vector Stores
                 </div>
                 <div className="flex items-center gap-2.5 px-3 py-2 hover:bg-white/5 rounded-xl text-white/50 hover:text-white/80 text-[13px] font-medium mb-6 transition-colors">
                   <Shield className="w-4 h-4" /> Governance Logs
                 </div>

                 <div className="text-[11px] font-semibold text-white/30 uppercase tracking-[0.15em] mb-4 pl-2">Deployments</div>
                 <div className="flex items-center gap-2.5 px-3 py-2 hover:bg-white/5 rounded-xl text-white/50 hover:text-white/80 text-[13px] font-medium mb-1 transition-colors">
                   <LayoutPanelTop className="w-4 h-4" /> Published Apps
                 </div>
                 <div className="flex items-center gap-2.5 px-3 py-2 hover:bg-white/5 rounded-xl text-white/50 hover:text-white/80 text-[13px] font-medium transition-colors">
                   <Code2 className="w-4 h-4" /> API Keys
                 </div>
               </div>

               {/* Main Canvas (Obsidian Data Presentation) */}
               <div className="flex-1 p-6 md:p-8 bg-[#050505]">
                 <div className="flex items-center justify-between mb-8 pb-4 border-b border-white/5">
                   <div>
                     <h3 className="text-[18px] font-medium text-white flex items-center gap-2">
                       Agent Trace <span className="text-white/30 font-light">/ pricing-agent-v2</span>
                     </h3>
                     <p className="text-[12px] text-white/40 mt-1">Session ID: trc_9f82a1b... · 12s ago</p>
                   </div>
                   <div className="flex items-center gap-2 bg-[#3fdca3]/10 text-[#3fdca3] border border-[#3fdca3]/20 px-3 py-1.5 rounded-lg text-[12px] font-medium">
                     <span className="w-1.5 h-1.5 rounded-full bg-[#3fdca3] animate-pulse" /> Running
                   </div>
                 </div>

                 {/* Trace visualization */}
                 <div className="space-y-4">
                   {[
                     { step: "User Input", detail: '"How does the enterprise tier compare to pro?"', time: "0ms", icon: User, color: "text-white/70" },
                     { step: "Graph Router", detail: "Selected sub-agent: pricing_specialist", time: "120ms", icon: Network, color: "text-[#3fdca3]" },
                     { step: "Knowledge Retrieval", detail: "Vector search hit · 4 passages resolved", time: "450ms", icon: Database, color: "text-[#8b5cf6]" },
                     { step: "Tool Execution", detail: "crm.lookup_entitlement()", time: "890ms", icon: Zap, color: "text-[#f59e0b]" },
                   ].map((log, i) => (
                     <div key={i} className="flex gap-4 group">
                       <div className="flex flex-col items-center">
                         <div className={`w-8 h-8 rounded-full bg-white/5 border border-white/10 flex items-center justify-center shrink-0 ${log.color}`}>
                           <log.icon className="w-3.5 h-3.5" />
                         </div>
                         {i !== 3 && <div className="w-[1px] h-full bg-white/5 my-1 group-hover:bg-white/20 transition-colors" />}
                       </div>
                       <div className="flex-1 bg-white/[0.02] border border-white/5 rounded-xl p-3 mb-2 flex justify-between items-start hover:border-white/10 transition-colors">
                         <div>
                           <div className="text-[13px] font-medium text-white/80">{log.step}</div>
                           <div className="text-[12px] text-white/40 mt-1 font-mono">{log.detail}</div>
                         </div>
                         <div className="text-[11px] text-white/30 font-mono">{log.time}</div>
                       </div>
                     </div>
                   ))}
                 </div>
               </div>
            </div>
         </div>
      </section>

      {/* Philosophy Section - Dub's structure + Obsidian's typography */}
      <section className="py-24 px-6 max-w-[1240px] mx-auto border-t border-white/5">
        <div className="max-w-2xl mb-16">
          <h2 className="font-serif-display text-[40px] leading-[1.1] text-white font-light mb-6">
            The foundation for <br className="hidden md:block"/> autonomous products.
          </h2>
          <p className="text-[16px] text-white/50 leading-relaxed font-sans-ui">
            We combined raw infrastructure logic with strict governance layers so your team can focus on agent behavior, not plumbing.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          {/* Pillar 1 */}
          <div className="bg-[#0a0a0a] border border-white/5 rounded-[24px] p-8 hover:border-white/15 transition-all group relative overflow-hidden">
            <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/10 blur-[50px] rounded-full group-hover:bg-blue-500/20 transition-colors" />
            <div className="w-12 h-12 bg-white/5 border border-white/10 rounded-2xl flex items-center justify-center mb-6 text-white/80 group-hover:text-white transition-colors">
              <Network className="w-5 h-5" />
            </div>
            <h3 className="text-[18px] font-medium text-white mb-3">Agent Graphs</h3>
            <p className="text-[14px] text-white/40 leading-relaxed font-light">
              Compose multi-step reasoning, tool usage, retrieval, and guardrails as a single, versioned deployable artifact.
            </p>
          </div>

          {/* Pillar 2 */}
          <div className="bg-[#0a0a0a] border border-white/5 rounded-[24px] p-8 hover:border-white/15 transition-all group relative overflow-hidden">
            <div className="absolute top-0 right-0 w-32 h-32 bg-green-500/10 blur-[50px] rounded-full group-hover:bg-green-500/20 transition-colors" />
            <div className="w-12 h-12 bg-white/5 border border-white/10 rounded-2xl flex items-center justify-center mb-6 text-white/80 group-hover:text-white transition-colors">
              <Database className="w-5 h-5" />
            </div>
            <h3 className="text-[18px] font-medium text-white mb-3">Knowledge Pipelines</h3>
            <p className="text-[14px] text-white/40 leading-relaxed font-light">
              Turn raw corporate content into retrieval-ready context with chunking operators, vector stores, and automatic lineage.
            </p>
          </div>

          {/* Pillar 3 */}
          <div className="bg-[#0a0a0a] border border-white/5 rounded-[24px] p-8 hover:border-white/15 transition-all group relative overflow-hidden">
            <div className="absolute top-0 right-0 w-32 h-32 bg-purple-500/10 blur-[50px] rounded-full group-hover:bg-purple-500/20 transition-colors" />
            <div className="w-12 h-12 bg-white/5 border border-white/10 rounded-2xl flex items-center justify-center mb-6 text-white/80 group-hover:text-white transition-colors">
              <Shield className="w-5 h-5" />
            </div>
            <h3 className="text-[18px] font-medium text-white mb-3">Runtime Governance</h3>
            <p className="text-[14px] text-white/40 leading-relaxed font-light">
              Every token, tool call, and knowledge hit is logged natively. Apply strict policy boundaries on AI actions in production.
            </p>
          </div>
        </div>
      </section>

      {/* Immersive Platform Feature - Obsidian OS Style Split */}
      <section className="py-24 px-6 border-t border-white/5 bg-[#050505]">
        <div className="max-w-[1240px] mx-auto grid md:grid-cols-[1.1fr_1fr] gap-16 items-center">
          
          {/* Left: Glass UI Overlaying moody background */}
          <div className="relative aspect-[4/3] rounded-[32px] bg-[#111] border border-white/5 overflow-hidden flex items-center justify-center">
            {/* Moody background abstract */}
            <div className="absolute inset-0 bg-gradient-to-br from-[#1c1c1c] to-[#050505]" />
            <div className="absolute w-[150%] h-[150%] bg-[radial-gradient(ellipse_at_center,rgba(255,255,255,0.03)_0%,transparent_50%)] top-[-25%] left-[-25%]" />
            
            {/* Overlay Dashboard Card (Dub cleanly structured inside glass) */}
            <div className="relative w-[85%] max-w-[420px] bg-[#1a1a1a]/80 backdrop-blur-2xl border border-white/10 rounded-2xl p-6 shadow-2xl">
               <div className="flex items-center justify-between mb-6 pb-4 border-b border-white/5">
                 <div className="text-[14px] font-medium text-white">App Revisions</div>
                 <div className="text-[12px] bg-white/10 text-white/80 px-2 py-0.5 rounded">customer-portal</div>
               </div>
               
               <div className="space-y-3">
                 {[
                   { id: "rev_84b39", status: "Active", author: "Daniel", time: "2h ago", active: true },
                   { id: "rev_72c11", status: "Rollback", author: "System", time: "1d ago", active: false },
                   { id: "rev_61a09", status: "Stale", author: "Sarah", time: "3d ago", active: false },
                 ].map((rev) => (
                   <div key={rev.id} className={`flex items-center justify-between p-3 rounded-xl border ${rev.active ? 'border-white/20 bg-white/5' : 'border-white/5 bg-white/[0.02]'} transition-colors`}>
                     <div className="flex items-center gap-3">
                       <div className={`w-2 h-2 rounded-full ${rev.active ? 'bg-[#3fdca3] shadow-[0_0_8px_#3fdca3]' : 'bg-white/20'}`} />
                       <div>
                         <div className="text-[13px] font-mono text-white/80">{rev.id}</div>
                         <div className="text-[11px] text-white/40 mt-0.5">{rev.author}</div>
                       </div>
                     </div>
                     <div className="text-right">
                       <div className="text-[12px] text-white/60">{rev.status}</div>
                       <div className="text-[11px] text-white/30 mt-0.5">{rev.time}</div>
                     </div>
                   </div>
                 ))}
               </div>
            </div>
          </div>

          {/* Right: Text content */}
          <div className="flex flex-col">
            <h2 className="font-serif-display text-[36px] md:text-[48px] font-light leading-[1.1] text-white mb-6">
              Ship with confidence.
            </h2>
            <p className="text-[16px] text-white/50 leading-relaxed font-sans-ui mb-10 max-w-md">
              Publish agent applications securely with built-in revision tracking, instant rollbacks, and multi-tenant data segregation natively isolated at the edge.
            </p>

            <div className="space-y-5">
               {[
                 { title: "Immutable revisions", desc: "Every deployment is snapshotted." },
                 { title: "Audit trails", desc: "Enterprise-grade logs for all model access." },
                 { title: "Role-based access", desc: "Control who can view traces and deploy." }
               ].map((item, i) => (
                 <div key={i} className="flex items-start gap-4">
                   <div className="w-6 h-6 rounded-full bg-white/5 border border-white/10 flex items-center justify-center shrink-0 mt-0.5 text-white/60">
                     <CheckCircle2 className="w-3.5 h-3.5" />
                   </div>
                   <div>
                     <div className="text-[15px] font-medium text-white mb-1">{item.title}</div>
                     <div className="text-[13px] text-white/40">{item.desc}</div>
                   </div>
                 </div>
               ))}
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section - Dub's structure (Center focused, precise UI elements) */}
      <section className="py-32 px-6 relative overflow-hidden border-t border-white/5">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.03)_0%,transparent_100%)]" />
        
        <div className="max-w-3xl mx-auto text-center relative z-10 bg-[#0a0a0a] border border-white/10 p-12 md:p-20 rounded-[40px] shadow-2xl">
           <h2 className="font-serif-display text-[40px] md:text-[56px] leading-[1.05] tracking-tight font-light text-white mb-6">
             Ready to build the future?
           </h2>
           <p className="text-[16px] md:text-[18px] text-white/50 font-sans-ui max-w-xl mx-auto mb-10">
             Join leading engineering teams building governed, scalable agent architectures on Talmudpedia today.
           </p>
           
           <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
             <Link href="/auth/login" className="w-full sm:w-auto px-8 py-4 bg-white text-black hover:bg-gray-100 text-[15px] font-medium rounded-full transition-colors shadow-lg">
               Create free account
             </Link>
             <Link href="/admin/apps" className="w-full sm:w-auto px-8 py-4 bg-[#111] border border-white/10 hover:bg-[#1a1a1a] text-white text-[15px] font-medium rounded-full transition-colors">
               Contact sales
             </Link>
           </div>
        </div>
      </section>

    </div>
  );
}

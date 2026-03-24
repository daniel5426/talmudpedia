"use client";

import Link from "next/link";
import { ChevronDown, Star, Link as LinkIcon, BarChart3, Users, LayoutGrid, CheckCircle2, DollarSign, Filter, Search } from "lucide-react";

export function LandingV6() {
  return (
    <div className="min-h-screen bg-white text-[#111827] font-sans overflow-x-hidden selection:bg-black selection:text-white pb-32">
      {/* Header */}
      <nav className="fixed top-0 z-50 w-full bg-white/95 backdrop-blur border-b border-gray-100 flex items-center h-16 pointer-events-auto">
        <div className="w-full max-w-7xl mx-auto px-6 flex items-center justify-between">
          <div className="flex items-center gap-8">
            <Link href="/" className="font-bold text-xl tracking-tight flex items-center gap-1.5">
              <span className="w-5 h-5 bg-black rounded-full flex items-center justify-center"></span>
              dub
            </Link>

            <div className="hidden lg:flex items-center gap-6 text-[14px] font-medium text-[#4b5563]">
              <button className="flex items-center gap-1 hover:text-black hover:bg-gray-50 px-2 py-1.5 rounded-md transition-colors">
                Product <ChevronDown className="w-3.5 h-3.5 opacity-60" />
              </button>
              <button className="flex items-center gap-1 hover:text-black hover:bg-gray-50 px-2 py-1.5 rounded-md transition-colors">
                Solutions <ChevronDown className="w-3.5 h-3.5 opacity-60" />
              </button>
              <button className="flex items-center gap-1 hover:text-black hover:bg-gray-50 px-2 py-1.5 rounded-md transition-colors">
                Resources <ChevronDown className="w-3.5 h-3.5 opacity-60" />
              </button>
              <Link href="#" className="hover:text-black hover:bg-gray-50 px-2 py-1.5 rounded-md transition-colors">Enterprise</Link>
              <Link href="#" className="hover:text-black hover:bg-gray-50 px-2 py-1.5 rounded-md transition-colors">Customers</Link>
              <Link href="#" className="hover:text-black hover:bg-gray-50 px-2 py-1.5 rounded-md transition-colors">Pricing</Link>
            </div>
          </div>

          <div className="hidden md:flex items-center gap-3 text-[14px] font-medium">
            <Link href="/auth/login" className="px-4 py-2 text-[#4b5563] bg-white border border-gray-200 hover:border-gray-300 rounded-full transition-colors shadow-[0_1px_2px_rgba(0,0,0,0.02)]">
              Log in
            </Link>
            <Link href="/auth/login" className="px-4 py-2 bg-black text-white hover:bg-gray-800 rounded-full transition-colors shadow-sm">
              Sign up
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative pt-16">
        <div className="relative mx-auto w-full bg-[#0a0a0a] min-h-[600px] flex flex-col items-center justify-start overflow-hidden border-b border-[#222]">
          
          {/* Subtle glow behind hero text */}
          <div className="absolute top-10 left-1/2 -translate-x-1/2 w-[600px] h-[300px] bg-white/[0.04] blur-[120px] rounded-full pointer-events-none" />

          {/* Grid lines */}
          <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff0a_1px,transparent_1px),linear-gradient(to_bottom,#ffffff0a_1px,transparent_1px)] bg-[size:48px_48px] [mask-image:radial-gradient(ellipse_100%_100%_at_50%_0%,black_10%,transparent_80%)]" />

          {/* SVG top cutout using paths that mimics the reference image exactly */}
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[64px] z-10">
            <svg 
              className="w-full h-full" 
              viewBox="0 0 800 64" 
              fill="none" 
              preserveAspectRatio="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path d="M0 0 H250 C290 0 310 64 360 64 H440 C490 64 510 0 550 0 H800 Z" fill="white" />
            </svg>
          </div>

          <div className="relative z-20 flex flex-col items-center text-center px-6 pt-32 pb-24 max-w-4xl w-full">
            <h1 className="text-white text-[56px] md:text-[68px] leading-[1.05] font-medium tracking-tight mb-6" style={{ wordSpacing: '-2px' }}>
              Supercharge your <br />
              <span className="opacity-[0.92]">marketing efforts</span>
            </h1>
            
            <p className="text-[#a1a1aa] text-[18px] md:text-[20px] leading-relaxed max-w-2xl font-light">
              See why Dub is the link attribution platform of choice for modern marketing teams.
            </p>

            <div className="flex flex-col sm:flex-row items-center gap-4 mt-10">
              <Link href="/auth/login" className="w-full sm:w-auto px-6 py-3 bg-white text-black text-[15px] font-medium rounded-full hover:bg-gray-100 transition-colors shadow-[0_0_15px_rgba(255,255,255,0.1)]">
                Start for free
              </Link>
              <Link href="/admin/apps" className="w-full sm:w-auto px-6 py-3 bg-white/10 text-white text-[15px] font-medium rounded-full hover:bg-white/15 transition-colors border border-white/5 backdrop-blur-md">
                Get a demo
              </Link>
            </div>

            <div className="flex flex-wrap items-center justify-center gap-6 mt-14 opacity-90">
              <div className="flex items-center gap-2.5">
                <span className="w-[18px] h-[18px] bg-white text-black font-bold text-[10px] flex items-center justify-center rounded pt-[1px]">G</span>
                <div className="flex gap-[1px]">
                  {[1,2,3,4,5].map(i => <Star key={i} className="h-[14px] w-[14px] fill-current text-white/90" />)}
                </div>
              </div>
              <div className="flex items-center gap-2.5">
                <span className="w-[18px] h-[18px] bg-[#ff6154] text-white font-bold text-[11px] flex items-center justify-center rounded-full leading-none">P</span>
                <div className="flex gap-[1px]">
                  {[1,2,3,4,5].map(i => <Star key={i} className="h-[14px] w-[14px] fill-current text-white/90" />)}
                </div>
              </div>
              <div className="flex items-center gap-2.5">
                <span className="w-[18px] h-[18px] bg-[#222] border border-white/10 text-white font-bold flex items-center justify-center rounded-full">
                  <Star className="h-[9px] w-[9px] fill-current text-white" />
                </span>
                <div className="flex gap-[1px]">
                  {[1,2,3,4,5].map(i => <Star key={i} className="h-[14px] w-[14px] fill-current text-white/90" />)}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Testimonial Section 1 */}
      <section className="relative bg-white py-16 border-b border-gray-100">
        <div className="absolute inset-0 bg-[radial-gradient(#e5e7eb_1.5px,transparent_1.5px)] bg-[size:24px_24px] opacity-60" />
        <div className="relative mx-auto max-w-4xl px-6">
          <div className="flex flex-col md:flex-row items-center md:items-start gap-10">
            <h2 className="text-[26px] md:text-[32px] leading-[1.4] font-medium text-[#111827] flex-1">
              "Dub has been a game-changer for our marketing campaigns. Our links get tens of millions of clicks monthly — with Dub, we are able to easily design our link previews, attribute clicks, and visualize our data."
            </h2>
            <div className="flex flex-col items-center md:items-end text-center md:text-right w-full md:w-auto shrink-0">
              <div className="flex items-center gap-2 text-xl font-bold mb-4">
                <div className="grid grid-cols-3 gap-0.5 w-[22px] h-[22px] rotate-45 text-[#3b82f6]">
                  {[...Array(9)].map((_, i) => (
                    <div key={i} className={`bg-current rounded-[1px] ${i === 4 ? 'opacity-0' : 'opacity-100'}`} />
                  ))}
                </div>
                perplexity
              </div>
              <div className="text-[14px] font-semibold text-[#111827]">Johnny Ho</div>
              <div className="text-[13px] text-gray-500 mb-4">Co-founder at Perplexity</div>
              <div className="w-10 h-10 rounded-full bg-gray-200 overflow-hidden border border-gray-100">
                <img src={`https://api.dicebear.com/7.x/notionists/svg?seed=johnny`} alt="Avatar" className="w-full h-full object-cover" />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Grid Integrations Section */}
      <section className="relative py-32 bg-white overflow-hidden border-b border-gray-100">
        <div className="absolute inset-0 grid grid-cols-[repeat(auto-fill,60px)] grid-rows-[repeat(auto-fill,60px)] [mask-image:linear-gradient(to_bottom,transparent,black_10%,black_90%,transparent)]">
          <div className="absolute inset-0 bg-[linear-gradient(to_right,#f3f4f6_1px,transparent_1px),linear-gradient(to_bottom,#f3f4f6_1px,transparent_1px)] bg-[size:60px_60px]" />
        </div>
        
        <div className="relative mx-auto max-w-6xl px-6 grid md:grid-cols-2 gap-16 items-center">
          <div className="max-w-md bg-white/60 p-6 md:p-0 rounded-3xl md:rounded-none backdrop-blur-md md:backdrop-blur-none shadow-xl shadow-gray-200/20 md:shadow-none ring-1 ring-gray-200/50 md:ring-0">
            <h2 className="text-[36px] md:text-[44px] leading-[1.05] tracking-tight font-medium text-[#111827] mb-6">
              Connect with your <br />
              favorite tools
            </h2>
            <p className="text-[16px] text-[#4b5563] mb-8 leading-relaxed max-w-[340px]">
              Extend Dub, streamline workflows, and connect your favorite tools, with new integrations added constantly.
            </p>
            <Link href="/admin/apps" className="inline-flex items-center px-5 py-2.5 text-[14px] font-medium text-[#111827] bg-white border border-gray-200 hover:border-gray-300 rounded-lg transition-colors shadow-[0_1px_2px_rgba(0,0,0,0.02)]">
              Explore integrations
            </Link>
          </div>

          <div className="relative h-[480px] w-full hidden md:block select-none pointer-events-none">
            {/* Floating Icons */}
            <div className="absolute top-[8%] left-[60%] w-[68px] h-[68px] bg-white rounded-2xl shadow-xl flex items-center justify-center p-3 border border-gray-100/50">
              <svg viewBox="0 0 256 256" className="w-full h-full text-[#95bf47] fill-current">
                <path d="M128 256C57.308 256 0 198.692 0 128S57.308 0 128 0s128 57.308 128 128-57.308 128-128 128z" fill="#FFF"/>
                <path d="M165.253 103.22c-8-3.047-19.42-7.518-19.42-12.87 0-4.634 5.37-6.096 11.536-6.096 9.4 0 17.514 3.064 24.363 8.16l14.453-24.96c-11.832-8.527-26.113-13.067-40.24-13.067-27.14 0-45.728 15.655-45.728 38.077 0 25.105 28.32 28.532 40.24 32.798 10.606 3.864 16.966 6.814 16.966 14.28 0 5.46-5.46 8.358-13.067 8.358-10.978 0-21.576-4.506-29.623-11.442v.01l-15.018 24.908c11.82 9.073 28.16 15.155 44.516 15.155 25.076 0 49.332-13.352 49.332-40.237-.002-22.383-16.797-27.42-38.308-33.07z"/>
                <path d="M83.433 118.006c-8.995 0-16.79-5.418-20.248-13.11l20.44-8.136c.928.948 2.08 1.488 3.518 1.488 2.768 0 4.887-1.896 4.887-4.66.012-3.79-5.207-3.097-15.542-8.49L76.5 61.218c-20.2-.42-36.46 15.6-36.88 35.804-.374 17.852 12.636 32.88 30.158 35.61l-10.74 27.618C44.3 151.72 40 137.96 40 123.635V56.634C39.46 22.183 23.33-1 23.33-1v200s22.95 24.717 48.692 24.717h.063c18.57 0 34.613-11.385 41.65-28.586l14.242-36.638C127.978 141.096 109.13 118.006 83.433 118.006z" />
              </svg>
            </div>

            <div className="absolute top-[28%] left-[25%] w-[68px] h-[68px] bg-white rounded-2xl shadow-xl flex items-center justify-center border border-gray-100/50">
              <svg viewBox="0 0 24 24" className="w-[42px] h-[42px] fill-current text-[#4A154B]">
                 <path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zm1.27 0a2.527 2.527 0 0 1 2.522-2.52 2.528 2.528 0 0 1 2.52 2.52v6.313A2.528 2.528 0 0 1 8.835 24a2.528 2.528 0 0 1-2.522-2.522v-6.313zM8.835 5.042a2.528 2.528 0 0 1 2.522-2.52A2.528 2.528 0 0 1 13.876 5.042a2.528 2.528 0 0 1-2.52 2.52h-2.52v-2.52zm-1.27 0a2.528 2.528 0 0 1-2.522 2.52 2.528 2.528 0 0 1-2.52-2.52V-1.27A2.528 2.528 0 0 1 5.042-3.792a2.527 2.527 0 0 1 2.522 2.522v6.312zm10.12 5.083a2.528 2.528 0 0 1 2.52-2.522 2.528 2.528 0 0 1 2.52 2.522 2.528 2.528 0 0 1-2.52 2.52h-2.52v-2.52zm-1.27 0a2.528 2.528 0 0 1-2.522 2.52 2.528 2.528 0 0 1-2.52-2.52V3.81a2.528 2.528 0 0 1 2.52-2.52 2.528 2.528 0 0 1 2.522 2.52v6.314zm-5.084 10.12a2.528 2.528 0 0 1-2.522 2.52 2.528 2.528 0 0 1-2.52-2.52 2.528 2.528 0 0 1 2.52-2.52h2.52v2.52zm1.27 0a2.528 2.528 0 0 1 2.522-2.52 2.528 2.528 0 0 1 2.52 2.52V25.27a2.528 2.528 0 0 1-2.52 2.522 2.527 2.527 0 0 1-2.522-2.522v-6.313z" transform="translate(4,4)"/>
              </svg>
            </div>

            <div className="absolute top-[48%] left-[46%] w-[68px] h-[68px] bg-white rounded-2xl shadow-xl flex items-center justify-center border border-gray-100/50">
              <svg viewBox="0 0 24 24" className="w-[42px] h-[42px] fill-[#6B4BFF] opacity-90">
                 <path d="M12 0l12 12-12 12L0 12 12 0zm0 4L4 12l8 8 8-8-8-8z"/>
              </svg>
            </div>

            <div className="absolute top-[28%] left-[80%] w-[68px] h-[68px] bg-white rounded-2xl shadow-xl flex items-center justify-center p-2.5 border border-gray-100/50">
               <div className="w-10 h-10 rounded-full bg-[#1e293b] text-white flex items-center justify-center font-serif text-[26px] font-bold">W</div>
            </div>

            <div className="absolute top-[65%] left-[10%] w-[68px] h-[68px] bg-[#3fdca3] text-white rounded-2xl shadow-xl flex items-center justify-center border border-gray-100/50">
               <svg viewBox="0 0 24 24" className="w-[32px] h-[32px] fill-current">
                  <path d="M3.75 6C3.75 4.757 4.757 3.75 6 3.75H18C19.243 3.75 20.25 4.757 20.25 6V18C20.25 19.243 19.243 20.25 18 20.25H6C4.757 20.25 3.75 19.243 3.75 18V6H3.75z"/>
                  <path stroke="currentColor" strokeWidth="2" strokeLinecap="round" d="M8 12h8m-8-4h8m-8 8h6"/>
               </svg>
            </div>

            <div className="absolute top-[60%] left-[82%] w-[68px] h-[68px] bg-[#635BFF] text-white rounded-2xl shadow-xl flex items-center justify-center font-bold text-[34px] font-italic border border-gray-100/50">
               S
            </div>

            <div className="absolute top-[82%] left-[46%] w-[68px] h-[68px] bg-[#FF4F00] text-white rounded-2xl shadow-xl flex items-center justify-center font-bold text-sm tracking-tight border border-gray-100/50">
               zapier
            </div>
            
            <div className="absolute top-[72%] left-[64%] w-[68px] h-[68px] bg-[#FF4C5A] text-white rounded-2xl shadow-xl flex items-center justify-center border border-gray-100/50">
               <div className="w-8 h-8 rounded border-2 border-white flex flex-col items-center justify-center overflow-hidden">
                 <div className="w-[12px] h-[2px] bg-white rotate-45 mb-1" />
                 <div className="w-[16px] h-[2px] bg-white -rotate-45" />
               </div>
            </div>

             <div className="absolute top-[88%] left-[86%] w-[68px] h-[68px] bg-white rounded-2xl shadow-xl flex items-center justify-center border border-gray-100/50">
               <div className="w-10 h-10 rounded bg-[#AA30FF] flex items-center justify-center px-1 font-bold text-white text-lg tracking-wider">
                 /\\/
               </div>
            </div>
          </div>
        </div>
      </section>

      {/* Product Section */}
      <section className="py-24 bg-white relative">
        <div className="max-w-7xl mx-auto px-6 text-center z-10 relative">
          
          <div className="flex items-center justify-center gap-4 text-sm font-medium mb-12 flex-wrap">
            <div className="flex items-center gap-2 bg-white px-4 py-2 border border-gray-200 rounded-full shadow-sm text-gray-700">
              <span className="w-4 h-4 bg-orange-100 rounded flex items-center justify-center text-orange-500"><LinkIcon className="w-2.5 h-2.5" /></span>
              Short Links
            </div>
            <div className="flex items-center gap-2 bg-gray-50 border border-gray-100 text-gray-500 hover:text-gray-800 hover:bg-white transition-colors cursor-pointer px-4 py-2 rounded-full shadow-[0_1px_2px_rgba(0,0,0,0.02)]">
              <span className="w-4 h-4 bg-green-100 rounded flex items-center justify-center text-green-500"><BarChart3 className="w-2.5 h-2.5" /></span>
              Conversion Analytics
            </div>
            <div className="flex items-center gap-2 bg-gray-50 border border-gray-100 text-gray-500 hover:text-gray-800 hover:bg-white transition-colors cursor-pointer px-4 py-2 rounded-full shadow-[0_1px_2px_rgba(0,0,0,0.02)]">
              <span className="w-4 h-4 bg-purple-100 rounded flex items-center justify-center text-purple-500"><Users className="w-2.5 h-2.5" /></span>
              Affiliate Programs
            </div>
          </div>

          <div className="inline-flex items-center justify-center px-4 py-1.5 border border-gray-200 rounded-full text-[13px] font-medium text-gray-600 mb-6 bg-white shadow-sm hover:bg-gray-50 transition-colors cursor-pointer ring-1 ring-gray-950/5">
            Celebrating $10M partner payouts on Dub <span className="ml-2 bg-gray-100 text-gray-500 rounded px-1 text-[10px]">Read more ↗</span>
          </div>

          <h2 className="text-[48px] md:text-[60px] font-medium tracking-tight text-[#111827] mb-6 leading-tight">
            Turn clicks into revenue
          </h2>
          <p className="text-[18px] md:text-[20px] text-[#4b5563] max-w-2xl mx-auto mb-10 font-normal leading-relaxed">
            Dub is the modern link attribution platform for short links, conversion tracking, and affiliate programs.
          </p>
          
          <div className="flex flex-col sm:flex-row justify-center gap-4">
            <Link href="/auth/login" className="bg-black text-white px-6 py-3 rounded-full font-medium hover:bg-gray-800 transition-colors shadow-lg">
              Start for free
            </Link>
            <Link href="/admin/apps" className="bg-white text-[#111827] border border-gray-200 px-6 py-3 rounded-full font-medium hover:bg-gray-50 transition-colors shadow-sm">
              Get a demo
            </Link>
          </div>

          {/* Web App UI Mockup */}
          <div className="mt-20 relative w-full max-w-[1000px] mx-auto z-10">
            <div className="absolute inset-0 bg-gradient-to-b from-[#f3f4f6]/50 to-white/0 translate-y-[20%]" />
            <div className="relative rounded-t-[32px] border border-gray-200/80 bg-white/40 p-3 shadow-[0_40px_100px_-20px_rgba(0,0,0,0.1)] backdrop-blur-2xl">
              <div className="bg-white rounded-t-[20px] border border-gray-200 shadow-sm flex min-h-[500px] overflow-hidden">
                 
                 {/* Sidebar */}
                 <div className="w-[240px] border-r border-gray-100 p-5 hidden md:flex flex-col bg-gray-50/50">
                    <div className="flex items-center gap-2 font-bold text-lg mb-8 text-black">
                      <span className="w-6 h-6 bg-black rounded-full flex items-center justify-center"></span> dub
                    </div>
                    
                    <div className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3 pl-2">Short Links</div>
                    <div className="flex items-center gap-2 p-2 rounded-xl bg-blue-50 text-blue-600 text-[14px] font-medium mb-1">
                      <LinkIcon className="w-4 h-4" strokeWidth={2.5} /> Links
                    </div>
                    <div className="flex items-center gap-2 p-2 rounded-xl text-gray-600 hover:bg-gray-100/80 text-[14px] font-medium mb-6">
                      <LayoutGrid className="w-4 h-4" strokeWidth={2.5} /> Domains
                    </div>

                    <div className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3 pl-2">Insights</div>
                    <div className="flex items-center gap-2 p-2 rounded-xl text-gray-600 hover:bg-gray-100/80 text-[14px] font-medium mb-1">
                      <BarChart3 className="w-4 h-4" strokeWidth={2.5} /> Analytics
                    </div>
                    <div className="flex items-center gap-2 p-2 rounded-xl text-gray-600 hover:bg-gray-100/80 text-[14px] font-medium mb-1">
                      <DollarSign className="w-4 h-4" strokeWidth={2.5} /> Events
                    </div>
                    <div className="flex items-center gap-2 p-2 rounded-xl text-gray-600 hover:bg-gray-100/80 text-[14px] font-medium mb-6">
                      <Users className="w-4 h-4" strokeWidth={2.5} /> Customers
                    </div>
                 </div>

                 {/* Main Dashboard Area */}
                 <div className="flex-1 p-6 lg:p-10 bg-white">
                    <div className="flex items-center justify-between mb-8">
                       <h2 className="text-[22px] font-semibold flex items-center gap-2 text-[#111827]">
                          Links <ChevronDown className="w-5 h-5 text-gray-400" />
                       </h2>
                       <button className="bg-black text-white px-3 py-1.5 rounded-lg text-sm font-medium shadow-sm flex items-center gap-2 hover:bg-gray-800 transition">
                         Create link <kbd className="text-white/60 bg-white/20 rounded px-1.5 py-0.5 text-[10px] ml-1 border border-white/10 font-sans">C</kbd>
                       </button>
                    </div>
                    
                    <div className="flex items-center gap-3 mb-6">
                      <button className="flex items-center gap-2 text-[14px] text-gray-600 bg-white border border-gray-200 px-3 py-1.5 rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.02)] hover:bg-gray-50">
                        <Filter className="w-4 h-4" /> Filter <ChevronDown className="w-4 h-4 ml-1 opacity-50" />
                      </button>
                      <button className="flex items-center gap-2 text-[14px] text-gray-600 bg-white border border-gray-200 px-3 py-1.5 rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.02)] hover:bg-gray-50">
                        <LayoutGrid className="w-4 h-4" /> Display <ChevronDown className="w-4 h-4 ml-1 opacity-50" />
                      </button>
                      <div className="ml-auto w-64 relative">
                        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                        <input type="text" placeholder="Search by short link or URL" className="w-full pl-9 pr-3 py-1.5 text-sm border border-gray-200 rounded-lg placeholder:text-gray-400 outline-none focus:ring-2 focus:ring-black/5" />
                      </div>
                    </div>

                    <div className="space-y-3">
                      {[
                        { short: "go.acme.com/launch", path: "acme.com/blog/announcements/new-feature", date: "Dec 10, 2025", clicks: "0", amount: "$0" },
                        { short: "go.acme.com/announcement", path: "acme.com/blog/announcement-blog", date: "Dec 9, 2025", clicks: "1.5K", amount: "$260" },
                        { short: "go.acme.com/signup", path: "acme.com/signup-today", date: "Dec 8, 2025", clicks: "1.5K", amount: "$0" },
                      ].map((item, i) => (
                        <div key={i} className="flex items-center justify-between p-4 rounded-xl border border-gray-200 hover:border-gray-300 transition-colors bg-white group shadow-[0_1px_2px_rgba(0,0,0,0.01)] cursor-pointer">
                          <div className="flex items-start gap-4">
                             <div className="w-9 h-9 rounded-full bg-gray-50 flex items-center justify-center border border-gray-200/80 group-hover:bg-white transition-colors shrink-0 object-cover overflow-hidden">
                                <img src={`https://api.dicebear.com/7.x/shapes/svg?seed=${item.short}`} alt="icon" className="w-6 h-6 mix-blend-multiply opacity-50" />
                             </div>
                             <div>
                               <div className="font-semibold text-[14px] text-gray-900 flex items-center gap-2">{item.short}</div>
                               <div className="text-[13px] text-gray-500 mt-1 flex items-center gap-2 truncate max-w-[400px]">
                                 <svg className="w-3.5 h-3.5 text-gray-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
                                 {item.path}
                                 <span className="w-1 h-1 bg-gray-300 rounded-full mx-0.5 shrink-0" />
                                 <img src={`https://api.dicebear.com/7.x/notionists/svg?seed=${i}`} className="w-4 h-4 rounded-full border border-gray-200" />
                                 <span className="shrink-0">{item.date}</span>
                               </div>
                             </div>
                          </div>
                          <div className="flex items-center gap-4 text-[13px] font-medium text-gray-600 bg-gray-50/80 px-3 py-1.5 rounded-lg border border-gray-100 group-hover:bg-white transition-colors">
                             <div className="flex items-center gap-1.5"><BarChart3 className="w-3.5 h-3.5" /> {item.clicks}</div>
                             <div className="flex items-center gap-1.5"><DollarSign className="w-3.5 h-3.5" /> {item.amount}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                 </div>

                 {/* Mock Dialog Overlay inside the window layer */}
                 <div className="absolute inset-0 bg-white/40 backdrop-blur-[2px] z-20 flex items-center justify-center -translate-y-[8px]">
                   <div className="bg-white rounded-2xl w-[600px] border border-gray-200/80 shadow-[0_0_40px_rgba(0,0,0,0.12)] origin-center overflow-hidden flex flex-col scale-[0.85] md:scale-100">
                     <div className="px-5 py-4 border-b border-gray-100 flex items-center gap-2 font-medium">
                       <LinkIcon className="w-4 h-4 text-gray-400" /> Links <ChevronDown className="w-4 h-4 text-gray-400 rotate-[-90deg]" /> New link
                       <button className="ml-auto w-6 h-6 flex items-center justify-center rounded-md hover:bg-gray-100 text-gray-500">
                         <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
                       </button>
                     </div>
                     <div className="p-6 bg-gray-50/30 flex gap-6">
                       <div className="flex-1 space-y-5">
                         <div>
                           <label className="text-[13px] font-medium text-gray-700 block mb-1.5">Destination URL</label>
                           <input type="text" value="http://acme.com/announcements/new-feature-launch" className="w-full border border-gray-200 rounded-lg px-3 py-2 text-[14px] text-gray-900 shadow-sm pointer-events-none" readOnly />
                         </div>
                         <div>
                           <label className="text-[13px] font-medium text-gray-700 block mb-1.5">Short link</label>
                           <div className="flex space-x-2">
                             <div className="bg-gray-50 border border-gray-200 border-r-0 rounded-l-lg px-3 py-2 text-[14px] text-gray-500 w-[140px] shrink-0 border-r border-gray-200/0 ring-1 ring-inset ring-gray-200">go.acme.com</div>
                             <input type="text" value="launch" className="flex-1 w-full border border-gray-200 text-gray-900 rounded-r-lg px-3 py-2 text-[14px] shadow-sm ml-0! pointer-events-none" readOnly />
                           </div>
                         </div>
                         <div>
                           <label className="text-[13px] font-medium text-gray-700 block mb-1.5">Tags</label>
                           <div className="border border-gray-200 rounded-lg p-2 flex gap-2 w-full bg-white shadow-sm">
                             <span className="bg-green-50 text-green-700 border border-green-200 px-2.5 py-1 rounded text-xs font-medium flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-green-500"></span>Blog</span>
                             <span className="bg-purple-50 text-purple-700 border border-purple-200 px-2.5 py-1 rounded text-xs font-medium flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-purple-500"></span>Marketing</span>
                           </div>
                         </div>
                       </div>
                       <div className="w-[180px] shrink-0 space-y-5">
                         <div>
                           <label className="text-[13px] font-medium text-gray-700 block mb-1.5">Folder</label>
                           <div className="border border-gray-200 rounded-lg px-3 py-2 bg-white flex items-center justify-between shadow-sm">
                             <div className="flex items-center gap-2 text-[13px] font-medium"><span className="w-2.5 h-2.5 rounded-[3px] bg-green-500 block"></span> Links</div>
                             <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
                           </div>
                         </div>
                         <div>
                           <label className="text-[13px] font-medium text-gray-700 block mb-1.5">QR Code</label>
                           <div className="border border-gray-200 rounded-lg bg-white p-4 shadow-sm h-[130px] flex items-center justify-center text-gray-300">
                             <LayoutGrid className="w-12 h-12" />
                           </div>
                         </div>
                       </div>
                     </div>
                     <div className="px-6 py-4 border-t border-gray-100 bg-gray-50 flex items-center justify-between">
                       <div className="flex gap-4">
                         {["UTM", "Targeting", "A/B Test", "Password", "Expiration"].map(tab => (
                           <div key={tab} className="text-[13px] font-medium text-gray-500 hover:text-gray-900 cursor-pointer">{tab}</div>
                         ))}
                       </div>
                       <button className="bg-black text-white px-4 py-2 rounded-lg text-sm font-medium shadow-sm flex items-center gap-1">Create link <kbd className="text-white/60 font-sans ml-1">↵</kbd></button>
                     </div>
                   </div>
                 </div>

              </div>

              {/* Black floating card over the mockup */}
              <div className="absolute -bottom-8 left-1/2 -translate-x-1/2 bg-[#111111] px-6 py-4 rounded-2xl shadow-2xl border border-gray-800 flex items-center gap-6 w-[max-content] z-30 transform hover:-translate-y-1 transition-transform">
                <div className="w-10 h-10 rounded-xl bg-white/10 flex items-center justify-center border border-white/10 shrink-0">
                  <LinkIcon className="w-5 h-5 text-white" />
                </div>
                <div>
                  <div className="text-white font-semibold text-[15px] tracking-tight">Short Links</div>
                  <div className="text-gray-400 text-[13px] font-medium mt-0.5">Create and manage short links at scale, with advanced features.</div>
                </div>
                <button className="ml-4 bg-white text-black px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-100 whitespace-nowrap">Learn more</button>
              </div>

            </div>
          </div>
        </div>
      </section>

      {/* Testimonial Section 2 */}
      <section className="relative bg-white py-24 mb-16 px-6">
        <div className="absolute inset-0 bg-[radial-gradient(#e5e7eb_1.5px,transparent_1.5px)] bg-[size:24px_24px] opacity-60" />
        <div className="relative mx-auto max-w-4xl pt-16 border-t border-gray-100">
          <div className="flex flex-col md:flex-row items-center md:items-start gap-10">
            <div className="flex-1 space-y-6">
              <h2 className="text-[26px] md:text-[32px] leading-[1.4] font-medium text-[#111827]">
                "Dub is the ultimate partner infrastructure for every startup. If you're looking to 10x your community / product-led growth – I cannot recommend building a partner program with Dub enough."
              </h2>
              <button className="text-[14px] font-medium text-[#6B4BFF] bg-[#6b4bff]/10 border border-[#6b4bff]/20 rounded-lg px-4 py-2 flex items-center gap-2 hover:bg-[#6b4bff]/15 transition-colors w-[fit-content]">
                <LayoutGrid className="w-4 h-4" /> Read the story
              </button>
            </div>
            
            <div className="flex flex-col items-center md:items-end text-center md:text-right shrink-0">
              <div className="flex items-center gap-2 text-2xl font-bold mb-4">
                <div className="flex gap-[-2px] text-black shrink-0 relative w-6 h-6">
                  {/* Framer triangle logo rough approx */}
                  <svg viewBox="0 0 24 24" className="w-full h-full fill-current">
                     <path d="M0 0h24v8h-8l8 8h-8v8l-8-8z"/>
                  </svg>
                </div>
                Framer
              </div>
              <div className="text-[14px] font-semibold text-[#111827]">Koen Bok</div>
              <div className="text-[13px] text-gray-500 mb-4">CEO at Framer</div>
              <div className="w-10 h-10 rounded-full bg-gray-200 overflow-hidden border border-gray-100">
                <img src={`https://api.dicebear.com/7.x/notionists/svg?seed=koen`} alt="Avatar" className="w-full h-full object-cover" />
              </div>
            </div>
          </div>
        </div>
      </section>

    </div>
  );
}

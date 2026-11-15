import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Sparkles, BookOpen, FileText, Globe, Layers, 
  ChevronDown, ArrowRight, Menu, X, Play, Check, Settings, AlertCircle, RefreshCw,
  LayoutDashboard, Users, FilePenLine, ShieldCheck, LogOut, AlertOctagon, Shield,
  Plus, Trash2, Pause, Terminal, MessageSquare, UploadCloud, ChevronLeft, ChevronRight,
  UserCog, ListOrdered, Paperclip, Upload, Save, Send, AlertTriangle, Info, PlusCircle,
  Eye, EyeOff
} from 'lucide-react';

const CONFIG = {
  APP_NAME: "AutoReach-AI",
  HERO_HEADLINE: "Say it. It's done.",
  HERO_SUBHEADLINE: "The words land in any app, exactly where your cursor is, cleanly. The brief written on the walk back. The reply ready before your hand reached the keyboard.",
  TAGLINES: [
    "Say it. It's done.",
    "Think it. Ship it.",
    "One click. Zero friction.",
    "Built while you blink.",
    "From thought to output. Instantly.",
    "Stop typing. Start flowing.",
    "The future is already here.",
  ],
  USE_CASES: [
    {
      role: "Accessibility",
      flow: "Flow for Accessibility",
      desc: "Dictate documents, navigate interfaces, and control workflows with extreme accuracy. Perfect for developers and writers seeking hands-free productivity.",
      cta: "Enable Flow Accessibility",
      image: "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=800&auto=format&fit=crop&q=80"
    },
    {
      role: "Creators",
      flow: "Flow for Creators",
      desc: "Draft video scripts, write blog posts, and capture brainstorming ideas at the speed of thought. Zero formatting friction.",
      cta: "Start Creating",
      image: "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800&auto=format&fit=crop&q=80"
    },
    {
      role: "Developers",
      flow: "Flow for Developers",
      desc: "Instantly draft project pitches, follow up on pull requests, or reach out to SDE hiring managers with your GitHub portfolio pre-linked.",
      cta: "Scale Outreach",
      image: "https://images.unsplash.com/photo-1618401471353-b98aedd07871?w=800&auto=format&fit=crop&q=80"
    },
    {
      role: "Sales",
      flow: "Flow for Sales Leads",
      desc: "Reach clients and follow up prospect lists with personalized voice templates converted instantly into high-deliverability emails.",
      cta: "Boost Reply Rates",
      image: "https://images.unsplash.com/photo-1556761175-5973dc0f32e7?w=800&auto=format&fit=crop&q=80"
    },
    {
      role: "Students",
      flow: "Flow for Students",
      desc: "Perfect for internship outreach. Automatically parses recruiter emails, references open roles, and attaches your resume dynamically.",
      cta: "Find Internships",
      image: "https://images.unsplash.com/photo-1523240795612-9a054b0db644?w=800&auto=format&fit=crop&q=80"
    }
  ],
  FOOTER_LINKS: {
    Company: [
      { label: "About", href: "#" },
      { label: "Careers", href: "#" },
      { label: "Blog", href: "#" }
    ],
    Product: [
      { label: "Features", href: "#" },
      { label: "Pricing", href: "#" },
      { label: "Integrations", href: "#" }
    ],
    Resources: [
      { label: "Documentation", href: "#" },
      { label: "Help Center", href: "#" },
      { label: "API Reference", href: "#" }
    ],
    Legal: [
      { label: "Privacy Policy", href: "/privacy" },
      { label: "Terms of Service", href: "/terms" },
      { label: "Refund Policy", href: "/refund-policy" }
    ]
  }
};

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 🌊 CURVED TEXT PATH ANIMATION
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
function CurvedTextPath() {
  return (
    <div className="absolute inset-0 pointer-events-none z-0 overflow-hidden select-none opacity-30">
      <svg viewBox="0 0 1000 400" className="w-full h-full overflow-visible">
        <path id="text-curve" d="M -100 250 C 200 400, 300 100, 650 300 C 850 400, 1100 200, 1200 280" fill="none" />
        <text className="font-serif italic text-xl fill-slate-800 tracking-widest uppercase">
          <textPath href="#text-curve" startOffset="0%">
            and see if the notes from yesterday's meeting were sent out, or if they're still waiting? I think check in with them and see what's going on...
            <animate attributeName="startOffset" from="0%" to="100%" dur="28s" repeatCount="indefinite" />
          </textPath>
        </text>
      </svg>
    </div>
  );
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 🎙️ VOICE WAVE INTERACTIVE BUTTON
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
function VoiceWaveButton() {
  const [isHovered, setIsHovered] = useState(false);
  
  return (
    <div 
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className="relative flex items-center gap-4 px-8 py-3.5 rounded-full border border-black/15 bg-white/70 hover:bg-white hover:border-black/35 hover:shadow-lg transition-all duration-350 cursor-pointer text-slate-900"
    >
      <div className="flex h-5 w-5 items-center justify-center rounded-full bg-slate-900 text-white">
        <span className="h-2.5 w-2.5 rounded-full bg-[#BCA1F7] animate-pulse" />
      </div>
      <span className="text-[11px] font-mono tracking-widest text-slate-800 uppercase font-bold">Say it. It's done.</span>
      <div className="flex items-center gap-0.75 h-5">
        {[...Array(14)].map((_, i) => {
          const height = isHovered 
            ? [10, 24, 16, 28, 12, 20, 24, 12, 18, 22, 14, 20, 12, 8][i] 
            : [6, 12, 8, 14, 6, 8, 12, 6, 8, 10, 8, 10, 6, 4][i];
          
          return (
            <motion.div
              key={i}
              animate={{ 
                height: isHovered ? [height * 0.5, height, height * 0.5] : height 
              }}
              transition={{ 
                repeat: Infinity, 
                duration: 0.6 + (i % 3) * 0.2, 
                ease: "easeInOut" 
              }}
              className="w-0.75 bg-slate-800 rounded-full"
              style={{ height: `${height}px` }}
            />
          );
        })}
      </div>
    </div>
  );
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 📱 DYNAMIC PARABOLIC ICON MARQUEE
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
function CurvedIconMarquee() {
  const icons = [
    "https://img.icons8.com/color/48/slack.png",
    "https://img.icons8.com/color/48/whatsapp.png",
    "https://img.icons8.com/color/48/gmail-new.png",
    "https://img.icons8.com/color/48/figma.png",
    "https://img.icons8.com/color/48/notion.png",
    "https://img.icons8.com/color/48/trello.png",
    "https://img.icons8.com/color/48/zoom.png",
    "https://img.icons8.com/color/48/spotify--v1.png",
    "https://img.icons8.com/color/48/discord-new-logo.png",
    "https://img.icons8.com/color/48/github.png"
  ];

  const [offset, setOffset] = useState(0);

  useEffect(() => {
    let animationId;
    const tick = () => {
      setOffset((prev) => (prev + 0.05) % 100);
      animationId = requestAnimationFrame(tick);
    };
    animationId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animationId);
  }, []);

  return (
    <div className="relative w-full h-32 overflow-hidden my-6 z-0 select-none">
      <div className="absolute inset-0">
        {[...Array(16)].map((_, index) => {
          const pos = (index * 7.5 + offset) % 120 - 10;
          const x = pos;
          // Smiley-curve formula: dip in the center (x = 50)
          const y = 15 + Math.pow((pos - 50) / 10, 2) * 2;
          const iconUrl = icons[index % icons.length];
          
          return (
            <div
              key={index}
              className="absolute bg-white/5 border border-white/10 rounded-2xl p-2 shadow-lg backdrop-blur-md flex items-center justify-center"
              style={{
                left: `${x}%`,
                top: `${y}px`,
                transform: 'translate(-50%, -50%)',
                width: '46px',
                height: '46px',
              }}
            >
              <img src={iconUrl} alt="App" className="w-8 h-8 object-contain" />
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 📱 INTERACTIVE MOCKUP PHONE COMPONENT
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
function InteractiveMockup() {
  const [messages, setMessages] = useState([]);
  const allMessages = [
    { sender: "other", text: "Cool, extra cream." },
    { sender: "other", text: "Also, are you still waiting on feedback on the org doc?" },
    { sender: "me", text: "All good there, the doc is fine." },
    { sender: "me", text: "Actually, wait, do we have the Q1 forecast?" }
  ];

  useEffect(() => {
    let index = 0;
    setMessages([allMessages[0]]);
    const interval = setInterval(() => {
      index = (index + 1) % (allMessages.length + 1);
      if (index === 0) {
        setMessages([]);
      } else {
        setMessages(allMessages.slice(0, index));
      }
    }, 3200);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="w-full max-w-sm rounded-[40px] border-4 border-white/10 bg-black/60 shadow-2xl p-4 min-h-[460px] flex flex-col justify-between relative overflow-hidden backdrop-blur-lg">
      <div className="absolute top-0 right-0 h-28 w-28 bg-[#BCA1F7]/5 blur-3xl rounded-full" />
      
      {/* Phone Header */}
      <div className="flex items-center justify-between border-b border-white/5 pb-3">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-full bg-slate-800 flex items-center justify-center text-xs font-bold text-white">J</div>
          <div>
            <h5 className="text-[11px] font-bold text-white">Jordan</h5>
            <span className="text-[8px] text-emerald-400 font-semibold flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-ping" /> Online
            </span>
          </div>
        </div>
        <div className="h-1.5 w-12 rounded-full bg-white/20 mx-auto" />
      </div>

      {/* Messages */}
      <div className="flex-1 py-4 space-y-3 overflow-y-auto">
        <AnimatePresence>
          {messages.map((msg, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 15, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              transition={{ duration: 0.3 }}
              className={`flex ${msg.sender === "me" ? "justify-end" : "justify-start"}`}
            >
              <div 
                className={`max-w-[80%] rounded-2xl px-4 py-2 text-xs font-medium leading-relaxed ${
                  msg.sender === "me" 
                    ? "bg-[#BCA1F7] text-slate-900 rounded-tr-none shadow-[0_0_12px_rgba(188,161,247,0.3)]" 
                    : "bg-white/10 text-slate-100 rounded-tl-none"
                }`}
              >
                {msg.text}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* Soundwave Visualizer in Mockup */}
      <div className="border-t border-white/5 pt-4 flex flex-col gap-3">
        <div className="flex items-center justify-between px-2">
          <span className="text-[9px] font-mono text-slate-500 uppercase tracking-widest">Whispr Engine</span>
          <span className="text-[9px] text-[#BCA1F7] font-semibold font-mono">Live Sync</span>
        </div>
        <div className="bg-white/5 rounded-2xl p-3 border border-white/5 flex items-center justify-between">
          <div className="flex items-center gap-0.5 flex-1 justify-center h-8">
            {[...Array(24)].map((_, i) => (
              <motion.div
                key={i}
                animate={{ 
                  height: [6, 26, 12, 30, 8, 18, 6][(i + Math.floor(Math.random() * 4)) % 7]
                }}
                transition={{ 
                  repeat: Infinity, 
                  duration: 0.5 + (i % 4) * 0.15,
                  ease: "easeInOut"
                }}
                className="w-0.75 bg-[#BCA1F7] rounded-full"
                style={{ height: '8px' }}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 🔒 LOGIN VIEW COMPONENT
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
function LoginView({ navigate }) {
  const [error] = useState(window.FLASK_ERROR || null);

  return (
    <div className="min-h-screen bg-[#FAF8F5] text-slate-900 flex items-center justify-center p-6 select-none font-sans relative overflow-hidden">
      {/* Curved Text Path ornament */}
      <CurvedTextPath />
      
      <div className="w-full max-w-md p-8 rounded-[40px] bg-[#0D0D10] text-slate-100 shadow-2xl border border-white/5 relative z-10">
        <div className="flex items-center gap-3 justify-center mb-6">
          <div className="flex h-9 w-9 items-center justify-center rounded-2xl bg-[#BCA1F7] text-slate-950 shadow-[0_0_12px_rgba(188,161,247,0.3)]">
            <Sparkles className="h-4.5 w-4.5" />
          </div>
          <span className="text-lg font-bold tracking-tight text-white font-serif">Flow</span>
        </div>

        <h2 className="text-2xl font-serif text-center mb-1 text-white">Log in to Flow</h2>
        <p className="text-[11px] text-slate-400 text-center mb-6 uppercase tracking-wider font-mono">Welcome back to your cockpit</p>

        {error && (
          <div className="mb-5 p-3.5 rounded-2xl border border-rose-500/20 bg-rose-500/10 text-rose-300 text-xs font-semibold flex items-center gap-2">
            <AlertTriangle className="h-4.5 w-4.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form action="/login" method="POST" className="space-y-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="email" className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Email Address</label>
            <input 
              type="email" 
              id="email" 
              name="email" 
              required 
              className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-2xl text-xs text-white placeholder-slate-500 outline-none focus:border-[#BCA1F7] focus:ring-1 focus:ring-[#BCA1F7] transition" 
              placeholder="you@example.com"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="password" className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Password</label>
            <input 
              type="password" 
              id="password" 
              name="password" 
              required 
              className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-2xl text-xs text-white placeholder-slate-500 outline-none focus:border-[#BCA1F7] focus:ring-1 focus:ring-[#BCA1F7] transition" 
              placeholder="••••••••"
            />
          </div>

          <motion.button 
            type="submit" 
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className="w-full bg-[#BCA1F7] text-slate-955 font-bold py-3.5 rounded-2xl transition mt-6 text-xs uppercase tracking-widest glowing-btn-accent border border-black/10 cursor-pointer"
          >
            Log In
          </motion.button>
        </form>

        <p className="mt-6 text-center text-xs text-slate-400">
          Don't have an account? <a href="/signup" className="text-[#BCA1F7] hover:underline font-semibold">Sign up</a>
        </p>
      </div>
    </div>
  );
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 🔒 SIGNUP VIEW COMPONENT
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
function SignupView({ navigate }) {
  const [error] = useState(window.FLASK_ERROR || null);

  return (
    <div className="min-h-screen bg-[#FAF8F5] text-slate-900 flex items-center justify-center p-6 select-none font-sans relative overflow-hidden">
      {/* Curved Text Path ornament */}
      <CurvedTextPath />

      <div className="w-full max-w-md p-8 rounded-[40px] bg-[#0D0D10] text-slate-100 shadow-2xl border border-white/5 relative z-10">
        <div className="flex items-center gap-3 justify-center mb-6">
          <div className="flex h-9 w-9 items-center justify-center rounded-2xl bg-[#BCA1F7] text-slate-950 shadow-[0_0_12px_rgba(188,161,247,0.3)]">
            <Sparkles className="h-4.5 w-4.5" />
          </div>
          <span className="text-lg font-bold tracking-tight text-white font-serif">Flow</span>
        </div>

        <h2 className="text-2xl font-serif text-center mb-1 text-white">Create Your Account</h2>
        <p className="text-[11px] text-slate-400 text-center mb-6 uppercase tracking-wider font-mono">Launch campaigns in under 5 minutes</p>

        {error && (
          <div className="mb-5 p-3.5 rounded-2xl border border-rose-500/20 bg-rose-500/10 text-rose-300 text-xs font-semibold flex items-center gap-2">
            <AlertTriangle className="h-4.5 w-4.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form action="/signup" method="POST" className="space-y-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="email" className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Email Address</label>
            <input 
              type="email" 
              id="email" 
              name="email" 
              required 
              className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-2xl text-xs text-white placeholder-slate-500 outline-none focus:border-[#BCA1F7] focus:ring-1 focus:ring-[#BCA1F7] transition" 
              placeholder="you@example.com"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="password" className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Password</label>
            <input 
              type="password" 
              id="password" 
              name="password" 
              required 
              className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-2xl text-xs text-white placeholder-slate-500 outline-none focus:border-[#BCA1F7] focus:ring-1 focus:ring-[#BCA1F7] transition" 
              placeholder="••••••••"
            />
          </div>

          <motion.button 
            type="submit" 
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className="w-full bg-[#BCA1F7] text-slate-955 font-bold py-3.5 rounded-2xl transition mt-6 text-xs uppercase tracking-widest glowing-btn-accent border border-black/10 cursor-pointer"
          >
            Create Account
          </motion.button>
        </form>

        <p className="mt-6 text-center text-xs text-slate-400">
          Already have an account? <a href="/login" className="text-[#BCA1F7] hover:underline font-semibold">Log in</a>
        </p>
      </div>
    </div>
  );
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 🔒 UNSUBSCRIBE VIEW COMPONENT
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
function UnsubscribeView({ token, navigate }) {
  const [email] = useState(window.UNSUBSCRIBE_EMAIL || "Your email address");

  return (
    <div className="min-h-screen bg-[#FAF8F5] text-slate-900 flex items-center justify-center p-6 select-none font-sans relative overflow-hidden">
      <CurvedTextPath />

      <div className="w-full max-w-md p-8 rounded-[40px] bg-[#0D0D10] text-slate-100 shadow-2xl border border-white/5 relative z-10 text-center space-y-6">
        <div className="h-16 w-16 rounded-full bg-[#BCA1F7]/10 text-[#BCA1F7] flex items-center justify-center border border-[#BCA1F7]/25 mx-auto shadow-[0_0_15px_rgba(188,161,247,0.2)]">
          <Check className="h-8 w-8" />
        </div>
        <div>
          <h2 className="text-2xl font-serif text-white mb-2">Unsubscribed</h2>
          <p className="text-slate-400 text-xs leading-relaxed max-w-xs mx-auto">
            <strong className="text-white font-mono">{email}</strong> has been successfully removed from this campaign outreach list.
          </p>
        </div>
        <p className="text-[10px] text-slate-500 font-mono tracking-wider uppercase">You will no longer receive sequence drip emails.</p>
        
        <button 
          onClick={() => navigate('/')} 
          className="inline-block text-xs uppercase tracking-widest text-[#BCA1F7] hover:text-[#BCA1F7]/80 font-bold transition"
        >
          &larr; Visit AutoReach-AI
        </button>
      </div>
    </div>
  );
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// ⚖️ LEGAL VIEW COMPONENT
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
function LegalView({ path, navigate }) {
  let title = "";
  let date = "May 21, 2026";
  let content = null;

  if (path === "/privacy") {
    title = "Privacy Policy";
    content = (
      <>
        <section>
          <h3 className="text-lg font-serif font-bold text-white mb-3">1. Information We Collect</h3>
          <p>When you create an account, we collect your <strong className="text-white">email address</strong> and a hashed password. When you connect a Google account via OAuth, we store an <strong className="text-white">OAuth access token</strong> and <strong className="text-white">refresh token</strong> to send emails on your behalf. We also retrieve your <strong className="text-white">Gmail address</strong> to display in your dashboard.</p>
          <p className="mt-2">We collect the email addresses of <strong className="text-white">contacts you upload</strong> via CSV. These are stored in our database solely to execute your email campaigns.</p>
        </section>
        <section>
          <h3 className="text-lg font-serif font-bold text-white mb-3">2. How We Use Your Data</h3>
          <ul className="list-disc list-inside space-y-1.5 text-slate-400">
            <li>To authenticate you and provide access to the platform.</li>
            <li>To send emails from your connected Gmail account(s) on your behalf.</li>
            <li>To personalize outgoing emails using the Gemini AI API (your email content is sent to Google's Gemini API for processing).</li>
            <li>To detect replies and classify them for your review.</li>
            <li>To process payments via Razorpay for subscription upgrades.</li>
          </ul>
        </section>
        <section>
          <h3 className="text-lg font-serif font-bold text-white mb-3">3. What We Do NOT Do</h3>
          <ul className="list-disc list-inside space-y-1.5 text-slate-400">
            <li>We do <strong className="text-[#BCA1F7]">not</strong> sell, rent, or share your personal data or email content with third parties for advertising purposes.</li>
            <li>We do <strong className="text-[#BCA1F7]">not</strong> use your email data to train machine learning models.</li>
            <li>We do <strong className="text-[#BCA1F7]">not</strong> store the content of emails you receive (only reply snippets for classification).</li>
          </ul>
        </section>
        <section>
          <h3 className="text-lg font-serif font-bold text-white mb-3">4. Data Storage & Security</h3>
          <p>Your data is stored in a managed PostgreSQL database hosted on secure cloud infrastructure. OAuth tokens are stored encrypted at rest. All connections use TLS encryption in transit.</p>
        </section>
        <section>
          <h3 className="text-lg font-serif font-bold text-white mb-3">5. Third-Party Services</h3>
          <ul className="list-disc list-inside space-y-1.5 text-slate-400 font-sans">
            <li><strong className="text-white">Google Gmail API</strong> — for sending emails and reading replies.</li>
            <li><strong className="text-white">Google Gemini API</strong> — for AI email personalization.</li>
            <li><strong className="text-white">Razorpay</strong> — for payment processing.</li>
            <li><strong className="text-white">Sentry</strong> — for error monitoring.</li>
            <li><strong className="text-white">PostHog</strong> — for anonymized product analytics.</li>
          </ul>
        </section>
        <section>
          <h3 className="text-lg font-serif font-bold text-white mb-3">6. Your Rights</h3>
          <p>You may revoke Google OAuth access at any time from your Google Account permissions page. You may request deletion of your account and all associated data by emailing us at the address below. We will process deletion requests within 30 days.</p>
        </section>
      </>
    );
  } else if (path === "/terms") {
    title = "Terms of Service";
    content = (
      <>
        <section>
          <h3 className="text-lg font-serif font-bold text-white mb-3">1. Service Description</h3>
          <p>AutoReach-AI ("the Service") is a SaaS platform that helps users send personalized email campaigns through their connected Gmail accounts. The Service uses Google's Gmail API to send emails and Google's Gemini AI to personalize email content.</p>
        </section>
        <section>
          <h3 className="text-lg font-serif font-bold text-white mb-3">2. Acceptable Use</h3>
          <p>By using the Service, you agree to:</p>
          <ul className="list-disc list-inside space-y-1.5 text-slate-400 mt-2">
            <li>Comply with the CAN-SPAM Act, GDPR, and all applicable anti-spam laws.</li>
            <li>Only send emails to contacts who have a legitimate business relationship or have opted in to receive communications.</li>
            <li>Include a valid physical postal address in your email content.</li>
            <li>Honor unsubscribe requests within 10 business days.</li>
            <li>Not use the Service for phishing, malware distribution, or any illegal activity.</li>
            <li>Not send deceptive, misleading, or fraudulent emails.</li>
          </ul>
        </section>
        <section>
          <h3 className="text-lg font-serif font-bold text-white mb-3">3. Account Responsibilities</h3>
          <p>You are responsible for maintaining the security of your account credentials and for all activities conducted under your account. You agree to notify us immediately if you become aware of any unauthorized use.</p>
        </section>
        <section>
          <h3 className="text-lg font-serif font-bold text-white mb-3">4. Google OAuth Authorization</h3>
          <p>By connecting your Google account, you authorize AutoReach-AI to send emails and read reply metadata on your behalf using the Gmail API. You may revoke this authorization at any time from your Google Account settings.</p>
        </section>
        <section>
          <h3 className="text-lg font-serif font-bold text-white mb-3">5. Subscription & Billing</h3>
          <p>Paid subscriptions are billed monthly via Razorpay. You may cancel your subscription at any time; cancellation takes effect at the end of the current billing cycle. See our Refund Policy for details.</p>
        </section>
        <section>
          <h3 className="text-lg font-serif font-bold text-white mb-3">6. Service Availability</h3>
          <p>We strive to maintain 99.9% uptime but do not guarantee uninterrupted access. We are not liable for any losses caused by service downtime, Gmail API rate limits, or Google's platform changes.</p>
        </section>
      </>
    );
  } else if (path === "/refund-policy") {
    title = "Refund & Cancellation Policy";
    content = (
      <>
        <section>
          <h3 className="text-lg font-serif font-bold text-white mb-3">1. Cancellation</h3>
          <p>You may cancel your subscription at any time from your dashboard Settings page. Upon cancellation:</p>
          <ul className="list-disc list-inside space-y-1.5 text-slate-400 mt-2">
            <li>Your subscription remains active until the end of the current billing cycle.</li>
            <li>You will not be charged for the next billing cycle.</li>
            <li>All campaign data and contacts remain accessible until the subscription expires.</li>
            <li>After expiration, your account reverts to the Free plan.</li>
          </ul>
        </section>
        <section>
          <h3 className="text-lg font-serif font-bold text-white mb-3">2. Refund Timeframes</h3>
          <div className="border border-white/10 rounded-2xl overflow-hidden mt-3 bg-white/[0.01]">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-white/10 bg-white/[0.02]">
                  <th className="px-5 py-4 text-white font-semibold font-serif">Timeframe</th>
                  <th className="px-5 py-4 text-[#BCA1F7] font-semibold font-serif">Refund Amount</th>
                  <th className="px-5 py-4 text-white font-semibold font-serif">Condition</th>
                </tr>
              </thead>
              <tbody className="text-slate-400">
                <tr className="border-b border-white/5">
                  <td className="px-5 py-3.5">Within 7 days</td>
                  <td className="px-5 py-3.5 text-[#BCA1F7] font-bold">100% refund</td>
                  <td className="px-5 py-3.5">No campaigns sent</td>
                </tr>
                <tr className="border-b border-white/5">
                  <td className="px-5 py-3.5">8–30 days</td>
                  <td className="px-5 py-3.5 text-amber-400 font-bold">Pro-rated refund</td>
                  <td className="px-5 py-3.5">Based on unused days</td>
                </tr>
                <tr>
                  <td className="px-5 py-3.5">After 30 days</td>
                  <td className="px-5 py-3.5 text-slate-500 font-bold">No refund</td>
                  <td className="px-5 py-3.5">Cancel next cycle</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
        <section>
          <h3 className="text-lg font-serif font-bold text-white mb-3">3. How to Request a Refund</h3>
          <p>Email <a href="mailto:billing@autoreach-ai.com" className="text-[#BCA1F7] hover:underline">billing@autoreach-ai.com</a> with your registered email address and reason. Refunds are processed within 5-7 business days via Razorpay.</p>
        </section>
      </>
    );
  } else {
    title = "Contact Us";
    content = (
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="p-5 rounded-2xl border border-white/10 bg-white/[0.01]">
          <h3 className="text-sm font-serif font-bold text-white mb-2">General Inquiries</h3>
          <p className="text-xs text-slate-400">Email: hello@autoreach-ai.com</p>
          <p className="text-[10px] text-slate-500 mt-1">Response time: Within 24 hours</p>
        </div>
        <div className="p-5 rounded-2xl border border-white/10 bg-white/[0.01]">
          <h3 className="text-sm font-serif font-bold text-white mb-2">Technical Support</h3>
          <p className="text-xs text-slate-400">Email: support@autoreach-ai.com</p>
          <p className="text-[10px] text-slate-500 mt-1">Response: 12h for Pro, 48h for Free</p>
        </div>
        <div className="p-5 rounded-2xl border border-white/10 bg-white/[0.01]">
          <h3 className="text-sm font-serif font-bold text-white mb-2">Billing & Payments</h3>
          <p className="text-xs text-slate-400">Email: billing@autoreach-ai.com</p>
          <p className="text-[10px] text-slate-500 mt-1">For cancellations, refunds, etc.</p>
        </div>
        <div className="p-5 rounded-2xl border border-white/10 bg-white/[0.01]">
          <h3 className="text-sm font-serif font-bold text-white mb-2">Registered Address</h3>
          <p className="text-xs text-slate-400">AutoReach-AI, India</p>
          <p className="text-[10px] text-slate-500 mt-1">Uptodate registration pending</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#FAF8F5] text-slate-900 py-16 px-6 font-sans">
      <div className="max-w-3xl mx-auto">
        <button 
          onClick={() => navigate('/')} 
          className="text-xs font-bold uppercase tracking-widest text-[#BCA1F7] hover:text-[#BCA1F7]/80 mb-8 flex items-center gap-1 transition"
        >
          &larr; Back to Home
        </button>

        <div className="w-full p-8 sm:p-12 rounded-[40px] bg-[#0D0D10] text-slate-305 shadow-2xl border border-white/5 space-y-6">
          <div>
            <h1 className="text-3xl sm:text-4xl font-serif text-white tracking-tight leading-tight">{title}</h1>
            <p className="text-[10px] text-slate-550 mt-1.5 uppercase font-mono tracking-wider">Last updated: {date}</p>
          </div>
          
          <div className="space-y-6 text-xs leading-relaxed border-t border-white/5 pt-6">
            {content}
          </div>
        </div>
      </div>
    </div>
  );
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 📊 SAAS COCKPIT DASHBOARD VIEW
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
function DashboardView({ navigate }) {
  const [currentTab, setCurrentTab] = useState("dashboard");
  const [campaigns, setCampaigns] = useState([]);
  const [activeCampaignId, setActiveCampaignId] = useState(null);
  const [status, setStatus] = useState({});
  const [config, setConfig] = useState({});
  const [logs, setLogs] = useState([]);
  const [pipeline, setPipeline] = useState({ raw_count: 0, dupes: 0, invalid: 0, ready: 0, filename: '', rejected_samples: [] });
  const [template, setTemplate] = useState({ subject: '', text: '', html: '' });
  const [senderProfile, setSenderProfile] = useState({ name: '', title: '', company: '', phone: '', website: '', linkedin: '', github: '', links: '', signature: 'Best,\n{{ sender_name }}' });
  const [settings, setSettings] = useState({ batch_size: 100, sleep_min: 180, sleep_max: 240, personalize_enabled: false, personalization_model: 'gemini-2.0-flash', personalization_prompt: '', gemini_api_key: '', sender: '', attachment: '' });
  const [toast, setToast] = useState({ show: false, message: '' });
  const [steps, setSteps] = useState([]);
  const [selectedStepId, setSelectedStepId] = useState(null);
  const [selectedStep, setSelectedStep] = useState({ id: null, step_number: 1, subject_template: '', text_template: '', html_template: '', delay_days: 3 });
  const [stepMetrics, setStepMetrics] = useState({});
  const [contactsList, setContactsList] = useState([]);
  const [replyDrafts, setReplyDrafts] = useState([]);
  const [userId, setUserId] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize] = useState(10);
  const [selectedContactId, setSelectedContactId] = useState(null);
  const [dnsCheckedDomain, setDnsCheckedDomain] = useState('');
  const [dnsResult, setDnsResult] = useState(null);
  const [dnsChecking, setDnsChecking] = useState(false);

  const logContainerRef = useRef(null);

  const tabs = [
    { id: 'dashboard', label: 'Cockpit Overview', icon: LayoutDashboard },
    { id: 'contacts', label: 'Leads Directory', icon: Users },
    { id: 'templates', label: 'Content Studio', icon: FilePenLine },
    { id: 'auth', label: 'Shield & APIs', icon: ShieldCheck },
  ];

  const showToast = (message) => {
    setToast({ show: true, message });
    const timer = setTimeout(() => setToast({ show: false, message: '' }), 3200);
    return () => clearTimeout(timer);
  };

  const formatNumber = (value) => Number(value || 0).toLocaleString();

  // Load reply drafts & campaigns initially
  useEffect(() => {
    const initFetch = async () => {
      const activeId = await loadCampaigns();
      await loadReplyDrafts();
      if (activeId) {
        await Promise.all([
          refreshStatus(activeId),
          refreshConfig(activeId),
          refreshLogs(activeId),
          loadSteps(activeId),
          loadContactsAndMetrics(activeId)
        ]);
      }
    };
    initFetch();
  }, []);

  // Reload details when campaign switches
  useEffect(() => {
    if (activeCampaignId) {
      refreshStatus(activeCampaignId);
      refreshConfig(activeCampaignId);
      refreshLogs(activeCampaignId);
      loadSteps(activeCampaignId);
      loadContactsAndMetrics(activeCampaignId);
    }
  }, [activeCampaignId]);

  // Logs terminal autoscroll
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs]);

  // Polling loop
  useEffect(() => {
    const interval = setInterval(() => {
      loadReplyDrafts();
      if (activeCampaignId) {
        refreshStatus(activeCampaignId);
        refreshLogs(activeCampaignId);
        loadContactsAndMetrics(activeCampaignId);
      }
    }, 4000);
    return () => clearInterval(interval);
  }, [activeCampaignId, userId]);

  const loadCampaigns = async (forceId = null) => {
    try {
      const res = await fetch('/api/campaigns');
      if (res.status === 401) { navigate('/login'); return null; }
      const data = await res.json();
      const list = data.campaigns || [];
      setCampaigns(list);
      if (list.length > 0) {
        const nextId = forceId || list[0].id;
        setActiveCampaignId(nextId);
        return nextId;
      }
    } catch (e) {
      console.error(e);
    }
    return null;
  };

  const switchCampaign = (id) => {
    const parsedId = parseInt(id);
    setActiveCampaignId(parsedId);
    setSteps([]);
    setSelectedStepId(null);
    setSelectedStep({ id: null, step_number: 1, subject_template: '', text_template: '', html_template: '', delay_days: 3 });
    setStepMetrics({});
    setContactsList([]);
  };

  const promptNewCampaign = async () => {
    const name = prompt("Enter a name for the new outreach campaign:");
    if (!name) return;
    try {
      const res = await fetch('/api/campaign/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
      });
      const data = await res.json();
      if (!res.ok) return showToast(data.error || 'Failed to create campaign');
      showToast(data.message);
      await loadCampaigns(data.campaign_id);
    } catch (err) {
      showToast('Network error while creating campaign.');
    }
  };

  const deleteCampaign = async () => {
    if (!activeCampaignId) return;
    if (!confirm("Are you sure you want to delete the active campaign? All contacts and logs will be permanently removed.")) return;
    try {
      const res = await fetch(`/api/campaign/delete/${activeCampaignId}`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) return showToast(data.error || 'Failed to delete campaign');
      showToast(data.message);
      setActiveCampaignId(null);
      await loadCampaigns();
    } catch (err) {
      showToast('Network error while deleting campaign.');
    }
  };

  const refreshStatus = async (id = activeCampaignId) => {
    if (!id) return;
    try {
      const res = await fetch(`/api/status?campaign_id=${id}`);
      if (res.status === 401) { navigate('/login'); return; }
      const data = await res.json();
      setStatus(data);
      if (data.user_id) setUserId(data.user_id);
    } catch (e) {
      console.error(e);
    }
  };

  const refreshConfig = async (id = activeCampaignId) => {
    if (!id) return;
    try {
      const res = await fetch(`/api/config?campaign_id=${id}`);
      if (res.status === 401) { navigate('/login'); return; }
      const data = await res.json();
      setConfig(data);
      if (data.user_id) setUserId(data.user_id);
      setTemplate({
        subject: data.subject || '',
        text: data.text_template || '',
        html: data.html_template || ''
      });
      setSenderProfile(data.sender_profile || { name: '', title: '', company: '', phone: '', website: '', linkedin: '', github: '', links: '', signature: 'Best,\n{{ sender_name }}' });
      setSettings({
        batch_size: data.batch_size,
        sleep_min: data.sleep_min,
        sleep_max: data.sleep_max,
        personalize_enabled: !!data.personalize_enabled,
        personalization_model: data.personalization_model,
        personalization_prompt: data.personalization_prompt || '',
        gemini_api_key: data.gemini_key_saved ? '********' : '',
        sender: data.sender || '',
        attachment: data.attachment || ''
      });
    } catch (e) {
      console.error(e);
    }
  };

  const refreshLogs = async (id = activeCampaignId) => {
    if (!id) return;
    try {
      const res = await fetch(`/api/logs?campaign_id=${id}&lines=60`);
      const data = await res.json();
      setLogs(data.logs || []);
    } catch (e) {
      console.error(e);
    }
  };

  const startCampaign = async () => {
    if (!activeCampaignId) return;
    await saveSettings(false);
    try {
      const res = await fetch('/api/campaign/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ campaign_id: activeCampaignId })
      });
      const data = await res.json();
      if (!res.ok) return showToast(data.error || 'Failed to start campaign');
      showToast(data.message);
      refreshStatus();
    } catch (err) {
      showToast('Network error while starting campaign.');
    }
  };

  const stopCampaign = async () => {
    if (!activeCampaignId) return;
    try {
      const res = await fetch('/api/campaign/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ campaign_id: activeCampaignId })
      });
      const data = await res.json();
      showToast(data.message);
      refreshStatus();
    } catch (err) {
      showToast('Network error while stopping campaign.');
    }
  };

  const handleFileUpload = async (event) => {
    if (!activeCampaignId) return;
    const file = event.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    formData.append('campaign_id', activeCampaignId);
    try {
      const res = await fetch('/api/upload-contacts', { method: 'POST', body: formData });
      const data = await res.json();
      if (!res.ok) return showToast(data.error || 'Upload failed');
      setPipeline(data.stats);
      showToast(data.message);
      refreshStatus();
      loadContactsAndMetrics();
    } catch (err) {
      showToast('Network error while uploading contacts.');
    }
  };

  const usePreset = (kind) => {
    const presets = {
      job: {
        subject: 'Quick note for {{ company }}',
        text: 'Hi {{ first_name or "there" }},\n\nI am {{ sender_name or "reaching out" }}{% if sender_title %}, {{ sender_title }}{% endif %}. I wanted to ask if {{ company or "your company" }} is open to relevant opportunities or conversations.\n\n{% if sender_linkedin or sender_github or sender_website or sender_links %}Links:\n{% if sender_linkedin %}- LinkedIn: {{ sender_linkedin }}\n{% endif %}{% if sender_github %}- GitHub: {{ sender_github }}\n{% endif %}{% if sender_website %}- Website: {{ sender_website }}\n{% endif %}{% if sender_links %}{{ sender_links }}\n{% endif %}\n{% endif %}I have attached my resume or supporting document for context.\n\n{{ sender_signature }}',
      },
      sales: {
        subject: 'Idea for {{ company }}',
        text: 'Hi {{ first_name or "there" }},\n\nI noticed {{ company or "your company" }} and wanted to share a quick idea that may help your team with your workflows.\n\nOpen to a short conversation this week?\n\n{% if sender_website or sender_links %}More context:\n{% if sender_website %}- {{ sender_website }}\n{% endif %}{% if sender_links %}{{ sender_links }}\n{% endif %}\n{% endif %}{{ sender_signature }}',
      }
    };
    if (selectedStepId && selectedStep) {
      setSelectedStep(prev => ({
        ...prev,
        subject_template: presets[kind].subject,
        text_template: presets[kind].text
      }));
    } else {
      setTemplate(prev => ({
        ...prev,
        subject: presets[kind].subject,
        text: presets[kind].text
      }));
    }
  };

  const loadSteps = async (id = activeCampaignId) => {
    if (!id) return;
    try {
      const res = await fetch(`/api/campaigns/${id}/steps`);
      const data = await res.json();
      const list = data.steps || [];
      setSteps(list);
      if (list.length > 0) {
        if (!selectedStepId || !list.some(s => s.id === selectedStepId)) {
          selectStep(list[0]);
        } else {
          const current = list.find(s => s.id === selectedStepId);
          if (current) selectStep(current);
        }
      } else {
        setSelectedStepId(null);
        setSelectedStep({ id: null, step_number: 1, subject_template: '', text_template: '', html_template: '', delay_days: 3 });
      }
    } catch (e) {
      console.error(e);
    }
  };

  const selectStep = (s) => {
    setSelectedStepId(s.id);
    setSelectedStep(JSON.parse(JSON.stringify(s)));
  };

  const addStep = async () => {
    if (!activeCampaignId) return;
    try {
      const res = await fetch(`/api/campaigns/${activeCampaignId}/steps`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          subject_template: 'Follow up: {{ subject }}',
          text_template: 'Hi {{ first_name }},\n\nJust following up on my last email.\n\nBest,\n{{ sender_name }}',
          html_template: '',
          delay_days: 3
        })
      });
      const data = await res.json();
      if (!res.ok) return showToast(data.error || 'Failed to add step');
      showToast('Sequence step added successfully');
      await loadSteps();
    } catch (err) {
      showToast('Network error while adding sequence step.');
    }
  };

  const deleteStep = async (stepId) => {
    if (!activeCampaignId) return;
    if (!confirm('Are you sure you want to delete this sequence step?')) return;
    try {
      const res = await fetch(`/api/campaigns/${activeCampaignId}/steps/${stepId}`, { method: 'DELETE' });
      const data = await res.json();
      if (!res.ok) return showToast(data.error || 'Failed to delete step');
      showToast('Sequence step deleted successfully');
      if (selectedStepId === stepId) {
        setSelectedStepId(null);
      }
      await loadSteps();
    } catch (err) {
      showToast('Network error while deleting sequence step.');
    }
  };

  const saveSelectedStep = async () => {
    if (!activeCampaignId || !selectedStepId) return;
    try {
      const res = await fetch(`/api/campaigns/${activeCampaignId}/steps/${selectedStepId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          subject_template: selectedStep.subject_template,
          text_template: selectedStep.text_template,
          html_template: selectedStep.html_template,
          delay_days: selectedStep.delay_days
        })
      });
      const data = await res.json();
      if (!res.ok) return showToast(data.error || 'Failed to save step templates');
      showToast('Step templates saved successfully');
      await loadSteps();
    } catch (err) {
      showToast('Network error while saving sequence step.');
    }
  };

  const loadContactsAndMetrics = async (id = activeCampaignId) => {
    if (!id) return;
    try {
      const res = await fetch(`/api/campaigns/${id}/contacts`);
      const data = await res.json();
      setStepMetrics(data.metrics || {});
      setContactsList(data.contacts || []);
    } catch (e) {
      console.error(e);
    }
  };

  const handleAttachmentUpload = async (event) => {
    if (!activeCampaignId) return;
    const file = event.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    formData.append('campaign_id', activeCampaignId);
    try {
      const res = await fetch('/api/upload-attachment', { method: 'POST', body: formData });
      const data = await res.json();
      if (!res.ok) return showToast(data.error || 'Attachment failed');
      setSettings(prev => ({ ...prev, attachment: data.attachment }));
      showToast(data.message);
      refreshConfig();
    } catch (err) {
      showToast('Network error while uploading proposal attachment.');
    }
  };

  const saveSettings = async (show = true) => {
    if (!activeCampaignId) return;
    try {
      const res = await fetch('/api/campaign/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          campaign_id: activeCampaignId,
          batch_size: settings.batch_size,
          sleep_min: settings.sleep_min,
          sleep_max: settings.sleep_max,
          subject: template.subject,
          attachment: settings.attachment,
          personalize_enabled: settings.personalize_enabled,
          personalization_model: settings.personalization_model,
          personalization_prompt: settings.personalization_prompt,
          gemini_api_key: settings.gemini_api_key === '********' ? '' : settings.gemini_api_key,
          sender_profile: senderProfile
        })
      });
      if (!res.ok) {
        if (show) showToast('Settings update failed');
        return;
      }
      if (show) showToast('Configuration settings updated successfully');
      refreshConfig();
    } catch (e) {
      if (show) showToast('Network error while saving settings.');
    }
  };

  const upgradePlan = async (tier) => {
    try {
      const res = await fetch('/api/razorpay/create-order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tier })
      });
      const data = await res.json();
      if (!res.ok) return showToast(data.error || 'Upgrade trigger failed');
      if (data.simulation) {
        window.location.href = data.url;
        return;
      }
      const options = {
        "key": data.key,
        "amount": data.amount,
        "currency": data.currency,
        "name": "AutoReach-AI",
        "description": "Pro Tier Subscription Upgrade",
        "order_id": data.order_id,
        "handler": async (response) => {
          const verifyRes = await fetch('/api/razorpay/verify-payment', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_order_id: response.razorpay_order_id,
              razorpay_signature: response.razorpay_signature,
              tier: tier
            })
          });
          const verifyData = await verifyRes.json();
          if (verifyRes.ok) {
            showToast('Payment verified & account upgraded to Pro!');
            await Promise.all([refreshStatus(), refreshConfig()]);
          } else {
            showToast(verifyData.error || 'Payment verification failed');
          }
        },
        "prefill": {
          "email": data.user_email,
          "name": data.user_name
        },
        "theme": {
          "color": "#BCA1F7"
        }
      };
      const rzp = new window.Razorpay(options);
      rzp.on('payment.failed', (response) => {
        showToast('Payment failed: ' + response.error.description);
      });
      rzp.open();
    } catch (err) {
      showToast('Network error during billing connection.');
    }
  };

  const simulateSandboxUpgrade = async () => {
    try {
      const res = await fetch('/api/sandbox/upgrade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tier: 'pro' })
      });
      const data = await res.json();
      if (res.ok) {
        showToast(data.message);
        refreshStatus();
        refreshConfig();
      }
    } catch (err) {
      showToast('Network error while requesting simulated sandbox upgrade.');
    }
  };

  const loadReplyDrafts = async () => {
    try {
      const res = await fetch('/api/reply-drafts');
      if (res.status === 401) { navigate('/login'); return; }
      const data = await res.json();
      const drafts = data.drafts || [];
      drafts.forEach(d => {
        const key = userId ? `autoreach_u_${userId}_draft_${d.id}` : `autoreach_draft_edit_${d.id}`;
        const localEdit = localStorage.getItem(key);
        if (localEdit !== null) {
          d.suggested_reply = localEdit;
        }
      });
      setReplyDrafts(drafts);
    } catch (e) {
      console.error(e);
    }
  };

  const saveReplyDraft = async (draftId, index) => {
    const draft = replyDrafts[index];
    if (!draft) return;
    try {
      const res = await fetch(`/api/reply-drafts/${draftId}/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ suggested_reply: draft.suggested_reply })
      });
      const data = await res.json();
      if (res.ok) {
        showToast('Reply draft saved successfully!');
      } else {
        showToast(data.error || 'Failed to save draft.');
      }
    } catch (e) {
      showToast('Network error while saving draft.');
    }
  };

  const sendReplyDraft = async (draftId, index) => {
    const draft = replyDrafts[index];
    if (!draft) return;
    try {
      const res = await fetch(`/api/reply-drafts/${draftId}/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reply_text: draft.suggested_reply })
      });
      const data = await res.json();
      if (res.ok) {
        showToast('AI Reply sent successfully!');
        const key = userId ? `autoreach_u_${userId}_draft_${draftId}` : `autoreach_draft_edit_${draftId}`;
        localStorage.removeItem(key);
        setReplyDrafts(prev => prev.filter((_, i) => i !== index));
      } else {
        showToast(data.error || 'Failed to send reply.');
      }
    } catch (e) {
      showToast('Network error while sending reply.');
    }
  };

  const discardReplyDraft = async (draftId, index) => {
    try {
      const res = await fetch(`/api/reply-drafts/${draftId}/discard`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await res.json();
      if (res.ok) {
        showToast('Draft dismissed.');
        const key = userId ? `autoreach_u_${userId}_draft_${draftId}` : `autoreach_draft_edit_${draftId}`;
        localStorage.removeItem(key);
        setReplyDrafts(prev => prev.filter((_, i) => i !== index));
      } else {
        showToast(data.error || 'Failed to discard draft.');
      }
    } catch (e) {
      showToast('Network error while discarding draft.');
    }
  };

  const disconnectInbox = async (tokenId) => {
    if (!confirm("Are you sure you want to disconnect this email inbox?")) return;
    try {
      const res = await fetch(`/api/auth/tokens/${tokenId}/delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await res.json();
      if (res.ok) {
        showToast(data.message || 'Inbox disconnected successfully.');
        await refreshConfig();
      } else {
        showToast(data.error || 'Failed to disconnect inbox.');
      }
    } catch (e) {
      showToast('Network error while disconnecting inbox.');
    }
  };

  const runDnsCheck = async () => {
    if (!dnsCheckedDomain) return;
    setDnsChecking(true);
    setDnsResult(null);
    try {
      const res = await fetch(`/api/dns-check?domain=${encodeURIComponent(dnsCheckedDomain)}`);
      const data = await res.json();
      if (res.ok) {
        setDnsResult(data);
      } else {
        showToast(data.error || 'Failed to check DNS records.');
      }
    } catch (err) {
      showToast('Network error during DNS validations.');
    } finally {
      setDnsChecking(false);
    }
  };

  // Directory Search / Page Mappings
  const filteredContacts = searchQuery
    ? contactsList.filter(c => 
        (c.email && c.email.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (c.first_name && c.first_name.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (c.last_name && c.last_name.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (c.company && c.company.toLowerCase().includes(searchQuery.toLowerCase()))
      )
    : contactsList;

  const totalPages = Math.ceil(filteredContacts.length / pageSize) || 1;
  const paginatedContacts = filteredContacts.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-[1440px] bg-[#FAF8F5] font-sans selection:bg-[#BCA1F7]/30 select-none text-slate-800">
      
      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          🔲 SIDEBAR NAVIGATION
          ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      <aside className="hidden w-72 shrink-0 border-r border-slate-200/80 px-6 py-6 lg:flex flex-col justify-between bg-white shadow-sm z-10">
        <div>
          {/* Brand logo */}
          <div className="mb-8 flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#0D0D10] text-[#BCA1F7] shadow-[0_0_12px_rgba(0,0,0,0.15)]">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <p className="text-base font-extrabold tracking-tight text-[#0D0D10] font-serif">Flow</p>
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">SaaS cockpit</p>
            </div>
          </div>

          {/* Tabs navigation */}
          <nav className="space-y-1">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = currentTab === tab.id;
              return (
                <button 
                  key={tab.id}
                  onClick={() => { setCurrentTab(tab.id); }}
                  className={`flex w-full items-center gap-3 rounded-2xl px-4 py-3.5 text-left text-xs font-semibold uppercase tracking-wider transition cursor-pointer ${
                    isActive 
                      ? 'bg-[#BCA1F7] text-slate-955 shadow-md border border-slate-955/10' 
                      : 'text-slate-500 hover:bg-black/5 hover:text-slate-900'
                  }`}
                >
                  <Icon className="h-4.5 w-4.5 shrink-0" />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </nav>
        </div>

        {/* Bottom sidebar status and profile */}
        <div className="space-y-4">
          {/* Active campaign status card */}
          <div className="bg-[#0D0D10] text-slate-200 rounded-[24px] p-4 border border-white/5 shadow-md">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400">Outreach Status</span>
              <span className={`h-2.5 w-2.5 rounded-full ${status.process_running ? 'bg-emerald-400 animate-pulse shadow-[0_0_8px_rgba(52,211,153,0.5)]' : 'bg-slate-600'}`} />
            </div>
            <p className="text-base font-extrabold text-white">{status.process_running ? 'Active Engine' : 'Idle'}</p>
            <p className="text-[10px] text-slate-400 mt-0.5">{config.auth_status || 'Checking Google...'}</p>
          </div>

          {/* User Profile */}
          <div className="flex items-center justify-between border-t border-slate-200/80 pt-4">
            <div className="flex items-center gap-2">
              <div className="h-8 w-8 rounded-full bg-[#0D0D10] border border-white/10 flex items-center justify-center font-bold text-[#BCA1F7] text-xs shadow-sm">
                U
              </div>
              <span className="text-xs font-bold text-slate-800">SaaS User</span>
            </div>
            <a 
              href="/logout" 
              onClick={() => {
                if (userId) {
                  Object.keys(localStorage)
                    .filter(key => key.startsWith('autoreach_u_' + userId + '_'))
                    .forEach(key => localStorage.removeItem(key));
                }
              }} 
              className="text-slate-400 hover:text-rose-500 transition" 
              title="Log out"
            >
              <LogOut className="h-4.5 w-4.5" />
            </a>
          </div>
        </div>
      </aside>

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          🔲 MAIN WORKSPACE
          ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      <main className="flex-1 px-4 py-6 sm:px-8 lg:px-10 overflow-y-auto">
        
        {/* Warning Banner for quarantined state */}
        {status.status === 'paused_no_active_inbox' && (
          <div className="mb-6 p-4 rounded-[24px] border border-rose-500/20 bg-rose-500/10 text-rose-800 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 shrink-0 rounded-2xl flex items-center justify-center bg-rose-500/20 text-rose-600 border border-rose-500/30">
                <AlertOctagon className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-extrabold text-rose-900">Campaign Paused: Inbox Shield Quarantined</p>
                <p className="text-xs text-rose-700 mt-0.5 leading-normal">
                  All connected email accounts have encountered authentication errors. Please reconnect healthy sending addresses in the <span className="font-bold underline cursor-pointer" onClick={() => setCurrentTab('auth')}>Shield & APIs tab</span> to resume outreach.
                </p>
              </div>
            </div>
            <button 
              onClick={() => setCurrentTab('auth')} 
              className="bg-rose-500 hover:bg-rose-600 text-white font-bold text-xs px-4 py-2 rounded-xl h-9 transition shrink-0 cursor-pointer shadow-sm"
            >
              Manage Inboxes
            </button>
          </div>
        )}

        {/* Quota Upgrade Banner */}
        <div className={`mb-6 flex flex-wrap items-center justify-between gap-4 p-4 rounded-[24px] border bg-gradient-to-r ${
          status.user_tier === 'pro' 
            ? 'from-emerald-500/10 to-slate-900/5 border-emerald-500/20 text-emerald-900' 
            : (status.user_tier === 'basic' ? 'from-indigo-500/10 to-slate-900/5 border-indigo-500/20 text-indigo-900' : 'from-[#0D0D10] to-[#121215] border-white/5 text-slate-300')
        }`}>
          <div className="flex items-center gap-3">
            <div className={`h-10 w-10 rounded-2xl flex items-center justify-center border ${
              status.user_tier === 'pro' 
                ? 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20' 
                : (status.user_tier === 'basic' ? 'bg-indigo-500/10 text-indigo-600 border-indigo-500/20' : 'bg-white/5 text-[#BCA1F7] border-white/10')
            }`}>
              <Shield className="h-5 w-5" />
            </div>
            <div>
              <p className="text-sm font-extrabold flex items-center gap-2">
                Account Tier: 
                <span className={`uppercase text-[9px] font-bold px-2.5 py-0.5 rounded-full ${
                  status.user_tier === 'pro' 
                    ? 'bg-emerald-500/20 text-emerald-700' 
                    : (status.user_tier === 'basic' ? 'bg-indigo-500/20 text-indigo-700' : 'bg-white/10 text-white')
                }`}>
                  {status.user_tier || 'free'}
                </span>
              </p>
              <p className="text-xs opacity-75 mt-0.5">
                {status.user_tier === 'pro' ? 'Full access unlocked including Gemini AI personalization.' : 'Upgrade to Pro to customize messages with Gemini.'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {status.user_tier !== 'pro' && (
              <button 
                onClick={() => upgradePlan('pro')} 
                className="bg-emerald-500 hover:bg-emerald-600 text-white font-bold text-xs px-4 py-2 rounded-xl h-9 transition cursor-pointer shadow-sm"
              >
                Upgrade to Pro
              </button>
            )}
            <button 
              onClick={() => simulateSandboxUpgrade()} 
              className="border border-slate-500/20 hover:bg-black/5 text-slate-700 font-bold text-xs px-4 py-2 rounded-xl h-9 cursor-pointer transition"
            >
              Simulate Pro
            </button>
          </div>
        </div>

        {/* Header Controls: Campaign selection switcher */}
        <header className="mb-6 flex flex-col gap-4 rounded-[32px] bg-[#0D0D10] text-slate-100 border border-white/5 p-6 lg:flex-row lg:items-center lg:justify-between shadow-lg">
          <div className="flex flex-col sm:flex-row sm:items-center gap-3.5">
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Active Campaign</label>
              <select 
                value={activeCampaignId || ''} 
                onChange={(e) => switchCampaign(e.target.value)} 
                className="w-full sm:w-60 px-3.5 py-2 bg-white/5 border border-white/10 rounded-xl text-xs text-white outline-none focus:border-[#BCA1F7] transition"
              >
                {campaigns.map(c => (
                  <option key={c.id} value={c.id} className="bg-[#0D0D10]">{c.name}</option>
                ))}
              </select>
            </div>
            <div className="flex gap-2 self-end sm:self-center mt-2 sm:mt-4">
              <button 
                onClick={() => promptNewCampaign()} 
                className="border border-white/10 hover:bg-white/5 text-slate-300 text-xs px-3 py-2 rounded-xl h-9 transition cursor-pointer"
              >
                <Plus className="h-4 w-4 inline mr-1" /> New Campaign
              </button>
              <button 
                onClick={() => deleteCampaign()} 
                className="border border-rose-500/20 hover:bg-rose-500/10 text-rose-400 text-xs px-3 py-2 rounded-xl h-9 transition cursor-pointer"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            {!status.process_running ? (
              <button 
                onClick={() => startCampaign()} 
                className="bg-[#BCA1F7] text-slate-950 font-bold px-6 py-2.5 rounded-xl text-xs uppercase tracking-widest glowing-btn-accent border border-black/10 transition cursor-pointer flex items-center gap-1.5"
              >
                <Play className="h-4 w-4 shrink-0 fill-current" /> Start Campaign
              </button>
            ) : (
              <button 
                onClick={() => stopCampaign()} 
                className="bg-rose-500 hover:bg-rose-600 text-white font-bold px-6 py-2.5 rounded-xl text-xs uppercase tracking-widest border border-rose-600 transition cursor-pointer flex items-center gap-1.5"
              >
                <Pause className="h-4 w-4 shrink-0" /> Pause Campaign
              </button>
            )}
          </div>
        </header>

        {/* Metrics Row */}
        <div className="mb-6 grid gap-4 grid-cols-2 lg:grid-cols-5 text-white">
          <div className="bg-[#0D0D10] border border-white/5 rounded-[24px] p-5 shadow-md">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Total Leads</p>
            <p className="mt-2 text-2xl font-extrabold text-white">{formatNumber(status.total_contacts)}</p>
          </div>
          <div className="bg-[#0D0D10] border border-white/5 rounded-[24px] p-5 shadow-md">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Successfully Sent</p>
            <p className="mt-2 text-2xl font-extrabold text-emerald-400">{formatNumber(status.emails_sent)}</p>
          </div>
          <div className="bg-[#0D0D10] border border-white/5 rounded-[24px] p-5 shadow-md">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Remaining Queue</p>
            <p className="mt-2 text-2xl font-extrabold text-[#BCA1F7]">{formatNumber(status.remaining)}</p>
          </div>
          <div className="bg-[#0D0D10] border border-white/5 rounded-[24px] p-5 shadow-md">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Failures / Bounces</p>
            <p className="mt-2 text-2xl font-extrabold text-rose-400">{formatNumber(status.emails_failed)}</p>
          </div>
          <div className="bg-[#0D0D10] border border-white/5 rounded-[24px] p-5 shadow-md">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Replies Detected</p>
            <p className="mt-2 text-2xl font-extrabold text-amber-400">{formatNumber(stepMetrics.replied || 0)}</p>
          </div>
        </div>

        {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            🔲 SCREEN: COCKPIT OVERVIEW TAB
            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
        {currentTab === 'dashboard' && (
          <div className="space-y-6">
            <div className="grid gap-6 xl:grid-cols-[1.1fr_.9fr]">
              {/* Progress panel */}
              <div className="bg-[#0D0D10] text-slate-200 rounded-[32px] p-6 border border-white/5 shadow-md flex flex-col justify-between">
                <div>
                  <h3 className="text-lg font-serif text-white font-bold">Campaign Delivery Progress</h3>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    Status: <span className="capitalize font-bold text-[#BCA1F7]">{status.status || 'stopped'}</span>
                  </p>
                </div>
                
                {/* Progress bar */}
                <div className="my-6">
                  <div className="h-3 overflow-hidden rounded-full bg-white/5 border border-white/10">
                    <div className="h-full rounded-full bg-[#BCA1F7]" style={{ width: `${status.progress_percent || 0}%` }} />
                  </div>
                  <div className="mt-2 flex justify-between text-[10px] font-mono font-bold text-slate-400 uppercase tracking-wider">
                    <span>{status.progress_percent || 0}% Complete</span>
                    <span>{status.emails_sent || 0} / {status.total_contacts || 0} Emails</span>
                  </div>
                </div>

                <div className="grid gap-3 grid-cols-3">
                  <div className="bg-white/5 rounded-2xl p-4 border border-white/5">
                    <p className="text-[9px] text-slate-400 uppercase font-bold tracking-wider">Index Pointer</p>
                    <p className="text-base font-bold text-white mt-1">{status.resume_point || 0}</p>
                  </div>
                  <div className="bg-white/5 rounded-2xl p-4 border border-white/5">
                    <p className="text-[9px] text-slate-400 uppercase font-bold tracking-wider">Batch Limit</p>
                    <p className="text-base font-bold text-white mt-1">{status.batch_size || 0} / day</p>
                  </div>
                  <div className="bg-white/5 rounded-2xl p-4 border border-white/5">
                    <p className="text-[9px] text-slate-400 uppercase font-bold tracking-wider">Delay Sleep</p>
                    <p className="text-base font-bold text-white mt-1">{status.sleep_min}-{status.sleep_max}s</p>
                  </div>
                </div>

                {/* Step indicators */}
                <div className="mt-6 grid gap-3 sm:grid-cols-4 text-xs font-bold font-sans">
                  <button onClick={() => setCurrentTab('auth')} className="rounded-2xl border border-white/5 bg-white/5 hover:bg-white/10 p-4 text-left transition cursor-pointer">
                    <span className="text-[9px] font-bold uppercase tracking-wider text-slate-500">Step 1</span>
                    <p className="mt-1 text-white">Auth APIs</p>
                  </button>
                  <button onClick={() => setCurrentTab('contacts')} className="rounded-2xl border border-white/5 bg-white/5 hover:bg-white/10 p-4 text-left transition cursor-pointer">
                    <span className="text-[9px] font-bold uppercase tracking-wider text-slate-500">Step 2</span>
                    <p className="mt-1 text-white">Leads CSV</p>
                  </button>
                  <button onClick={() => setCurrentTab('templates')} className="rounded-2xl border border-white/5 bg-white/5 hover:bg-white/10 p-4 text-left transition cursor-pointer">
                    <span className="text-[9px] font-bold uppercase tracking-wider text-slate-500">Step 3</span>
                    <p className="mt-1 text-white">Write Studio</p>
                  </button>
                  <button onClick={() => startCampaign()} className="rounded-2xl bg-[#BCA1F7] text-slate-950 p-4 text-left transition glowing-btn-accent border border-black/10 cursor-pointer">
                    <span className="text-[9px] font-bold uppercase tracking-wider text-slate-950/70">Step 4</span>
                    <p className="mt-1">Send Mail</p>
                  </button>
                </div>
              </div>

              {/* Logs terminal widget */}
              <div className="bg-[#0D0D10] text-slate-200 rounded-[32px] p-6 border border-white/5 shadow-md flex flex-col justify-between h-[340px]">
                <div className="mb-4 flex items-center justify-between">
                  <h3 className="text-sm font-bold uppercase tracking-wider text-white flex items-center gap-2">
                    <Terminal className="h-4.5 w-4.5 text-[#BCA1F7]" /> Active Logs Terminal
                  </h3>
                  <button 
                    onClick={() => refreshLogs()} 
                    className="rounded-full border border-white/10 px-3.5 py-1 text-[9px] uppercase tracking-wider font-mono font-bold hover:bg-white/5 transition"
                  >
                    Refresh
                  </button>
                </div>
                
                <div 
                  ref={logContainerRef} 
                  className="flex-1 overflow-y-auto rounded-2xl bg-[#030712] p-4 font-mono text-[10px] leading-5 border border-white/5"
                >
                  {logs.map((log, i) => (
                    <p 
                      key={i} 
                      className={`mb-1 ${
                        log.type === 'success' 
                          ? 'text-emerald-400' 
                          : (log.type === 'error' ? 'text-rose-400' : (log.type === 'warning' ? 'text-amber-400' : 'text-slate-400'))
                      }`}
                    >
                      <span className="text-slate-600">&gt;</span> {log.raw}
                    </p>
                  ))}
                  {logs.length === 0 && (
                    <p className="text-slate-600 font-mono">Waiting for campaign events log output...</p>
                  )}
                </div>
              </div>
            </div>

            {/* Funnel Breakdown */}
            <div className="bg-[#0D0D10] text-slate-200 rounded-[32px] p-6 border border-white/5 shadow-md">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-4 flex items-center gap-2">
                <Layers className="h-4 w-4 text-[#BCA1F7]" /> Sequence Funnel Breakdown
              </h4>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {steps.map((s, idx) => (
                  <div 
                    key={s.id} 
                    className="p-4 rounded-2xl bg-white/5 border border-white/5 hover:border-[#BCA1F7]/30 transition"
                  >
                    <div className="flex items-center gap-2.5 mb-2.5">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[#BCA1F7]/10 text-[#BCA1F7] font-bold border border-[#BCA1F7]/25 text-xs">
                        {idx + 1}
                      </div>
                      <div className="min-w-0">
                        <p className="text-xs font-bold truncate text-white">{s.subject_template || '(no subject)'}</p>
                        <p className="text-[9px] text-slate-505 font-mono uppercase tracking-wider mt-0.5">
                          {idx === 0 ? 'First Step (Immediate)' : `Wait ${s.delay_days} days`}
                        </p>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-[9px] font-mono font-bold uppercase tracking-wider">
                      <div className="bg-slate-905 p-1.5 rounded flex justify-between text-slate-400">
                        <span>Pending</span>
                        <span>{stepMetrics[`step_${idx + 1}_pending`] || 0}</span>
                      </div>
                      <div className="bg-emerald-955/40 p-1.5 rounded flex justify-between text-emerald-400">
                        <span>Sent</span>
                        <span>{stepMetrics[`step_${idx + 1}_sent`] || 0}</span>
                      </div>
                      <div className="bg-amber-955/40 p-1.5 rounded flex justify-between text-amber-400">
                        <span>Replied</span>
                        <span>{stepMetrics[`step_${idx + 1}_replied`] || 0}</span>
                      </div>
                      <div className="bg-slate-905 p-1.5 rounded flex justify-between text-slate-500">
                        <span>Done</span>
                        <span>{stepMetrics[`step_${idx + 1}_completed`] || 0}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              {steps.length === 0 && (
                <p className="text-slate-500 text-xs text-center py-6">No sequence steps defined. Go to Content Studio to build sequence steps.</p>
              )}
            </div>

            {/* AI objection queue handler */}
            <div className="bg-[#0D0D10] text-slate-200 rounded-[32px] p-6 border border-white/5 shadow-md">
              <div className="mb-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <h3 className="text-lg font-serif text-white font-bold flex items-center gap-2">
                    <MessageSquare className="h-5 w-5 text-[#BCA1F7]" /> AI Objection Handler & Reply Queue
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">Review, edit, and send objections and interest replies drafted automatically by Gemini.</p>
                </div>
                {replyDrafts.length > 0 && (
                  <span className="text-[10px] font-mono uppercase tracking-wider font-extrabold text-[#BCA1F7] bg-[#BCA1F7]/10 border border-[#BCA1F7]/20 px-3 py-1 rounded-full self-start">
                    {replyDrafts.length} Pending
                  </span>
                )}
              </div>

              <div className="space-y-4">
                {replyDrafts.map((draft, idx) => (
                  <div key={draft.id} className="p-5 rounded-2xl bg-white/5 border border-white/5 hover:border-[#BCA1F7]/25 transition space-y-4">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-white/5 pb-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-white">{draft.contact_name || 'Prospect'}</span>
                          <span className="text-[10px] text-slate-400 font-mono">&lt;{draft.contact_email}&gt;</span>
                        </div>
                        <p className="text-[10px] text-slate-500 uppercase font-mono tracking-wider mt-0.5">Campaign: {draft.campaign_name}</p>
                      </div>
                      <div className="flex items-center gap-2 font-mono text-[9px] font-bold">
                        <span className={`px-2.5 py-1 rounded-full uppercase ${
                          draft.classification === 'interested' 
                            ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' 
                            : (draft.classification === 'objection' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' : 'bg-rose-500/10 text-rose-400 border border-rose-500/20')
                        }`}>
                          {draft.classification}
                        </span>
                        <span className="text-slate-500">{new Date(draft.created_at).toLocaleDateString()}</span>
                      </div>
                    </div>

                    <div className="bg-[#090D16] p-4 rounded-xl border border-white/5">
                      <p className="text-[9px] font-mono uppercase tracking-wider text-slate-500 mb-1">Incoming Reply Snippet</p>
                      <p className="text-xs text-slate-300 italic leading-relaxed">“{draft.reply_snippet}”</p>
                    </div>

                    <div>
                      <p className="text-[9px] font-mono uppercase tracking-wider text-slate-500 mb-1">AI Suggested Objection-Handling Response</p>
                      <textarea 
                        value={draft.suggested_reply} 
                        onChange={(e) => {
                          const val = e.target.value;
                          const next = [...replyDrafts];
                          next[idx].suggested_reply = val;
                          setReplyDrafts(next);
                          const key = userId ? `autoreach_u_${userId}_draft_${draft.id}` : `autoreach_draft_edit_${draft.id}`;
                          localStorage.setItem(key, val);
                        }}
                        rows="4" 
                        className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-2xl text-xs text-white outline-none focus:border-[#BCA1F7] transition"
                        placeholder="Type custom reply..."
                      />
                    </div>

                    <div className="flex justify-end gap-3 pt-1 text-xs">
                      <button 
                        onClick={() => discardReplyDraft(draft.id, idx)} 
                        className="px-4 py-2 border border-white/10 rounded-xl hover:bg-white/5 text-slate-300 transition cursor-pointer"
                      >
                        Dismiss Draft
                      </button>
                      <button 
                        onClick={() => saveReplyDraft(draft.id, idx)} 
                        className="px-4 py-2 border border-white/10 rounded-xl hover:bg-white/5 text-slate-300 transition cursor-pointer"
                      >
                        Save Draft
                      </button>
                      <button 
                        onClick={() => sendReplyDraft(draft.id, idx)} 
                        className="bg-[#BCA1F7] text-slate-950 font-bold px-5 py-2 rounded-xl border border-black/10 transition cursor-pointer flex items-center gap-1"
                      >
                        <Send className="h-3.5 w-3.5" /> Send Reply
                      </button>
                    </div>
                  </div>
                ))}

                {replyDrafts.length === 0 && (
                  <div className="text-center py-10">
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-500/10 text-emerald-400 mx-auto mb-3 border border-emerald-500/20 shadow-sm">
                      <Check className="h-5 w-5" />
                    </div>
                    <h4 className="text-sm font-bold text-slate-200">Inbox is completely clear</h4>
                    <p className="text-xs text-slate-500 mt-1">No pending prospect replies. You're all caught up! ✨</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            🔲 SCREEN: LEADS DIRECTORY TAB
            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
        {currentTab === 'contacts' && (
          <div className="space-y-6">
            <div className="mb-4">
              <h3 className="text-2xl font-serif text-slate-955 font-bold">Leads Directory & Ingestion</h3>
              <p className="text-xs text-slate-505 mt-0.5">Upload recipient spreadsheets. AutoReach parses matching email rows and filters duplicates automatically.</p>
            </div>
            
            <div className="grid gap-6 xl:grid-cols-[1fr_.8fr]">
              <label className="bg-[#0D0D10] text-slate-200 rounded-[32px] border-2 border-dashed border-white/15 p-8 text-center flex flex-col items-center justify-center cursor-pointer hover:bg-white/5 transition duration-200 min-h-[260px]">
                <input type="file" id="fileUpload" className="hidden" accept=".csv,.txt" onChange={handleFileUpload} />
                <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-3xl bg-[#BCA1F7]/10 text-[#BCA1F7] border border-[#BCA1F7]/25 shadow-sm">
                  <UploadCloud className="h-7 w-7" />
                </div>
                <h4 className="text-lg font-bold text-white">Import spreadsheet contacts file</h4>
                <p className="mt-1.5 max-w-sm text-[11px] text-slate-400 leading-normal font-sans">Requires a column with 'email' header format. Invalid rows will be filtered out to optimize success.</p>
                {pipeline.filename && (
                  <p className="mt-3 rounded-full bg-[#BCA1F7]/15 border border-[#BCA1F7]/20 px-3.5 py-1 text-[9px] font-bold text-[#BCA1F7] font-mono">
                    Uploaded: {pipeline.filename}
                  </p>
                )}
                <span className="mt-5 rounded-2xl bg-[#BCA1F7] text-slate-950 px-6 py-2 text-xs font-bold glowing-btn-accent border border-black/10 transition">
                  Select File
                </span>
              </label>

              <div className="bg-[#0D0D10] text-slate-200 rounded-[32px] p-6 border border-white/5 shadow-md flex flex-col justify-between">
                <div>
                  <h4 className="mb-4 text-base font-extrabold text-white">Pipeline Data Output</h4>
                  <div className="space-y-2.5">
                    <div className="bg-white/5 border border-white/5 flex items-center justify-between rounded-xl p-3.5">
                      <span className="text-xs text-slate-400">Total Rows Found</span>
                      <span className="font-mono font-bold text-sm text-white">{pipeline.raw_count}</span>
                    </div>
                    <div className="bg-white/5 border border-white/5 flex items-center justify-between rounded-xl p-3.5">
                      <span className="text-xs text-slate-400">Duplicates Filtered</span>
                      <span className="font-mono font-bold text-amber-400 text-sm">{pipeline.dupes}</span>
                    </div>
                    <div className="bg-white/5 border border-white/5 flex items-center justify-between rounded-xl p-3.5">
                      <span className="text-xs text-slate-400">Invalid Emails Ignored</span>
                      <span className="font-mono font-bold text-rose-400 text-sm">{pipeline.invalid}</span>
                    </div>
                    <div className="flex items-center justify-between rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3.5">
                      <span className="text-xs font-bold text-emerald-400">Imported Successfully</span>
                      <span className="font-mono text-lg font-extrabold text-emerald-400">{pipeline.ready}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {contactsList.length > 0 && (
              <div className="bg-[#0D0D10] text-slate-200 rounded-[32px] p-6 border border-white/5 shadow-md">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
                  <div>
                    <h4 className="text-base font-bold text-white">Imported Leads Directory</h4>
                    <p className="text-[11px] text-slate-400 mt-0.5">Review parsed columns, status, and custom variables extracted for personalization.</p>
                  </div>
                  <div className="relative w-full sm:w-72">
                    <input 
                      type="text" 
                      value={searchQuery}
                      onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1); }}
                      placeholder="Search email, name, company..." 
                      className="w-full py-2.5 pl-10 pr-4 bg-white/5 border border-white/10 rounded-xl text-xs text-white placeholder-slate-500 outline-none focus:border-[#BCA1F7] transition"
                    />
                    <div className="absolute left-3.5 top-3 text-slate-500">
                      <ChevronRight className="h-4.5 w-4.5" />
                    </div>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-white/5 text-slate-500 font-bold uppercase tracking-wider">
                        <th className="pb-3 px-4">Recipient</th>
                        <th className="pb-3 px-4">Company</th>
                        <th className="pb-3 px-4">Status</th>
                        <th className="pb-3 px-4">Sequence Step</th>
                        <th className="pb-3 px-4 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {paginatedContacts.map((contact) => (
                        <React.Fragment key={contact.id}>
                          <tr className="border-b border-white/5 hover:bg-white/[0.02] transition">
                            <td className="py-3.5 px-4">
                              <div className="font-bold text-white">{`${contact.first_name || ''} ${contact.last_name || ''}`.trim() || 'No Name'}</div>
                              <div className="text-[10px] text-slate-500 font-mono mt-0.5">{contact.email}</div>
                            </td>
                            <td className="py-3.5 px-4 text-slate-300">{contact.company || '—'}</td>
                            <td className="py-3.5 px-4">
                              <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[9px] font-bold uppercase tracking-wider border ${
                                contact.status === 'sent' || contact.status === 'completed'
                                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/25'
                                  : (contact.status === 'failed' 
                                      ? 'bg-rose-500/10 text-rose-400 border-rose-500/25' 
                                      : (contact.status === 'replied' ? 'bg-amber-500/10 text-amber-400 border-amber-500/25' : 'bg-slate-800 text-slate-400 border-slate-700'))
                              }`}>
                                <span className={`h-1.5 w-1.5 rounded-full ${
                                  contact.status === 'sent' || contact.status === 'completed' ? 'bg-emerald-400' : (contact.status === 'failed' ? 'bg-rose-400' : (contact.status === 'replied' ? 'bg-amber-400' : 'bg-slate-400'))
                                }`} />
                                {contact.status}
                              </span>
                            </td>
                            <td className="py-3.5 px-4">
                              <span className="inline-flex h-5.5 w-5.5 items-center justify-center rounded-lg bg-white/5 border border-white/10 text-[10px] font-mono font-bold text-slate-300">
                                S{contact.current_step}
                              </span>
                            </td>
                            <td className="py-3.5 px-4 text-right">
                              <button 
                                onClick={() => setSelectedContactId(selectedContactId === contact.id ? null : contact.id)} 
                                className="text-xs font-bold text-[#BCA1F7] hover:underline transition"
                              >
                                {selectedContactId === contact.id ? 'Hide Variables' : 'Inspect'}
                              </button>
                            </td>
                          </tr>

                          {selectedContactId === contact.id && (
                            <tr className="bg-white/[0.01]">
                              <td colSpan="5" className="py-4 px-6 border-b border-white/5">
                                <div className="bg-white/5 rounded-2xl p-4 border border-white/5 text-left">
                                  <div className="flex items-center justify-between mb-3 border-b border-white/5 pb-2 text-[10px] uppercase font-mono font-bold text-slate-500">
                                    <span>Extracted CSV Field Mappings</span>
                                    <span>Contact ID: {contact.id}</span>
                                  </div>
                                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                                    {Object.entries(contact.raw_variables || {}).map(([key, val]) => (
                                      <div key={key} className="bg-white/5 rounded-xl p-2.5 border border-white/[0.05] flex items-center justify-between gap-3 overflow-hidden">
                                        <span className="text-[10px] font-mono text-slate-505 shrink-0">{`{{ ${key} }}`}</span>
                                        <span className="text-xs font-bold text-slate-200 truncate" title={val}>{val || '—'}</span>
                                      </div>
                                    ))}
                                    {(!contact.raw_variables || Object.keys(contact.raw_variables).length === 0) && (
                                      <p className="text-xs text-slate-500 italic">No variables found.</p>
                                    )}
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="flex items-center justify-between border-t border-white/5 mt-4 pt-4 text-xs font-mono">
                  <span className="text-slate-500 font-bold uppercase tracking-wider">
                    Showing {((currentPage - 1) * pageSize) + 1} to {Math.min(currentPage * pageSize, filteredContacts.length)} of {filteredContacts.length} leads
                  </span>
                  <div className="flex items-center gap-3">
                    <button 
                      onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))} 
                      disabled={currentPage === 1}
                      className="bg-white/5 flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 hover:bg-white/10 disabled:opacity-30 transition cursor-pointer text-white"
                    >
                      <ChevronLeft className="h-4 w-4" />
                    </button>
                    <span className="text-slate-300 font-bold">Page {currentPage} of {totalPages}</span>
                    <button 
                      onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))} 
                      disabled={currentPage === totalPages}
                      className="bg-white/5 flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 hover:bg-white/10 disabled:opacity-30 transition cursor-pointer text-white"
                    >
                      <ChevronRight className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            🔲 SCREEN: CONTENT STUDIO TAB
            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
        {currentTab === 'templates' && (
          <div className="space-y-6">
            <div className="mb-4">
              <h3 className="text-2xl font-serif text-slate-955 font-bold">Content Studio</h3>
              <p className="text-xs text-slate-505 mt-0.5">Design multi-step email drip sequences. Add sequential steps, specify delay intervals, and write templates.</p>
            </div>

            <div className="grid gap-6 xl:grid-cols-[1.1fr_1.9fr]">
              <div className="space-y-6">
                {/* Sender profile parameters */}
                <div className="bg-[#0D0D10] text-slate-200 rounded-[32px] p-6 border border-white/5 shadow-md">
                  <h4 className="text-sm font-bold uppercase tracking-wider text-white mb-4 flex items-center gap-2">
                    <UserCog className="h-4.5 w-4.5 text-[#BCA1F7]" /> Sender Sign-off Profile
                  </h4>
                  <div className="space-y-3.5">
                    <input 
                      type="text" 
                      value={senderProfile.name} 
                      onChange={(e) => setSenderProfile({ ...senderProfile, name: e.target.value })} 
                      className="w-full px-3.5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-xs text-white placeholder-slate-500 outline-none focus:border-[#BCA1F7] transition"
                      placeholder="Full name (e.g. Priya Sharma)"
                    />
                    <input 
                      type="text" 
                      value={senderProfile.title} 
                      onChange={(e) => setSenderProfile({ ...senderProfile, title: e.target.value })} 
                      className="w-full px-3.5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-xs text-white placeholder-slate-500 outline-none focus:border-[#BCA1F7] transition"
                      placeholder="Job title / tagline"
                    />
                    <input 
                      type="text" 
                      value={senderProfile.company} 
                      onChange={(e) => setSenderProfile({ ...senderProfile, company: e.target.value })} 
                      className="w-full px-3.5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-xs text-white placeholder-slate-500 outline-none focus:border-[#BCA1F7] transition"
                      placeholder="Sender company / college"
                    />
                    <input 
                      type="text" 
                      value={senderProfile.phone} 
                      onChange={(e) => setSenderProfile({ ...senderProfile, phone: e.target.value })} 
                      className="w-full px-3.5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-xs text-white placeholder-slate-500 outline-none focus:border-[#BCA1F7] transition"
                      placeholder="Phone contact, optional"
                    />
                    <input 
                      type="url" 
                      value={senderProfile.linkedin} 
                      onChange={(e) => setSenderProfile({ ...senderProfile, linkedin: e.target.value })} 
                      className="w-full px-3.5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-xs text-white placeholder-slate-500 outline-none focus:border-[#BCA1F7] transition"
                      placeholder="LinkedIn URL"
                    />
                    <input 
                      type="url" 
                      value={senderProfile.github} 
                      onChange={(e) => setSenderProfile({ ...senderProfile, github: e.target.value })} 
                      className="w-full px-3.5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-xs text-white placeholder-slate-500 outline-none focus:border-[#BCA1F7] transition"
                      placeholder="GitHub URL"
                    />
                    <input 
                      type="url" 
                      value={senderProfile.website} 
                      onChange={(e) => setSenderProfile({ ...senderProfile, website: e.target.value })} 
                      className="w-full px-3.5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-xs text-white placeholder-slate-500 outline-none focus:border-[#BCA1F7] transition"
                      placeholder="Portfolio website URL"
                    />
                    <textarea 
                      value={senderProfile.links} 
                      onChange={(e) => setSenderProfile({ ...senderProfile, links: e.target.value })} 
                      rows="3" 
                      className="w-full px-3.5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-[11px] font-mono text-white placeholder-slate-500 outline-none focus:border-[#BCA1F7] transition"
                      placeholder="Extra Links (one per line)"
                    />
                    <textarea 
                      value={senderProfile.signature} 
                      onChange={(e) => setSenderProfile({ ...senderProfile, signature: e.target.value })} 
                      rows="3" 
                      className="w-full px-3.5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-[11px] font-mono text-white placeholder-slate-500 outline-none focus:border-[#BCA1F7] transition"
                      placeholder="Best,\n{{ sender_name }}"
                    />
                    <button 
                      onClick={() => saveSettings()} 
                      className="w-full bg-[#BCA1F7] text-slate-950 font-bold py-2.5 rounded-xl text-xs uppercase tracking-widest glowing-btn-accent border border-black/10 transition cursor-pointer"
                    >
                      Save Profile Data
                    </button>
                  </div>
                </div>

                {/* Sequence steps list manager */}
                <div className="bg-[#0D0D10] text-slate-200 rounded-[32px] p-6 border border-white/5 shadow-md">
                  <div className="mb-4 flex items-center justify-between">
                    <h4 className="text-sm font-bold uppercase tracking-wider text-white flex items-center gap-2">
                      <ListOrdered className="h-4.5 w-4.5 text-[#BCA1F7]" /> Drip Sequence Steps
                    </h4>
                    <button 
                      onClick={() => addStep()} 
                      className="border border-[#BCA1F7]/20 hover:bg-[#BCA1F7]/10 text-[#BCA1F7] font-bold text-[10px] font-mono uppercase tracking-wider px-3 py-1.5 rounded-xl h-8 cursor-pointer"
                    >
                      Add Step
                    </button>
                  </div>
                  <div className="space-y-2 max-h-[300px] overflow-y-auto pr-1">
                    {steps.map((s, idx) => (
                      <div 
                        key={s.id}
                        onClick={() => selectStep(s)}
                        className={`p-3.5 rounded-2xl border transition cursor-pointer flex items-center justify-between gap-3 ${
                          selectedStepId === s.id 
                            ? 'border-[#BCA1F7] bg-[#BCA1F7]/5' 
                            : 'border-white/5 bg-white/5 hover:bg-white/10'
                        }`}
                      >
                        <div className="min-w-0 flex-1">
                          <p className="text-xs font-bold truncate text-white">{`Step ${s.step_number}: ${s.subject_template || '(no subject)'}`}</p>
                          <p className="text-[10px] text-slate-500 font-mono mt-0.5">
                            {s.step_number === 1 ? 'Sends immediately (0 day delay)' : `Wait ${s.delay_days} days after previous step`}
                          </p>
                        </div>
                        <button 
                          onClick={(e) => { e.stopPropagation(); deleteStep(s.id); }} 
                          className="text-slate-500 hover:text-rose-400 p-1.5 rounded-lg hover:bg-rose-500/10 transition cursor-pointer shrink-0"
                          title="Delete Step"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    ))}
                    {steps.length === 0 && (
                      <p className="text-slate-505 text-xs text-center py-6">No sequence steps defined. Add a step to get started.</p>
                    )}
                  </div>
                </div>

                {/* Campaign attachments options */}
                <div className="bg-[#0D0D10] text-slate-200 rounded-[32px] p-6 border border-white/5 shadow-md">
                  <h4 className="text-sm font-bold uppercase tracking-wider text-white mb-4">Campaign Options</h4>
                  <div className="rounded-2xl bg-white/5 border border-white/5 p-4">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <div>
                        <p className="text-xs font-bold text-white">Campaign File Attachment</p>
                        <p className="text-[10px] text-slate-500 mt-0.5">Attach PDF proposals, resumes, or brochures.</p>
                      </div>
                      <Paperclip className="h-4.5 w-4.5 text-[#BCA1F7]" />
                    </div>
                    <input type="file" id="templateAttachmentUpload" className="hidden" accept=".pdf,.doc,.docx,.txt,.png,.jpg,.jpeg" onChange={handleAttachmentUpload} />
                    <div className="flex flex-wrap items-center gap-2">
                      <button 
                        onClick={() => document.getElementById('templateAttachmentUpload').click()} 
                        className="border border-white/10 hover:bg-white/5 text-xs px-3 py-1.5 rounded-xl h-9 cursor-pointer transition flex items-center gap-1 text-slate-200"
                      >
                        <Upload className="h-3.5 w-3.5" /> Upload
                      </button>
                      {settings.attachment && (
                        <>
                          <span className="text-[10px] font-mono font-bold text-[#BCA1F7] truncate max-w-40" title={settings.attachment}>
                            {settings.attachment.split('/').pop()}
                          </span>
                          <button onClick={() => { setSettings({ ...settings, attachment: '' }); saveSettings(); }} className="text-slate-500 hover:text-slate-350 text-[10px] font-bold underline cursor-pointer">
                            Remove
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Editor for selected Step */}
              <div className="bg-[#0D0D10] text-slate-200 rounded-[32px] p-6 border border-white/5 shadow-md">
                {selectedStepId ? (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between pb-3 border-b border-white/5">
                      <h4 className="text-base font-extrabold text-white">Editing Step {selectedStep.step_number}</h4>
                      <div className="flex items-center gap-2.5">
                        <label className="text-[9px] font-mono font-bold uppercase tracking-wider text-slate-505">Delay</label>
                        <input 
                          type="number" 
                          min="0" 
                          max="60" 
                          value={selectedStep.delay_days}
                          onChange={(e) => setSelectedStep({ ...selectedStep, delay_days: parseInt(e.target.value) || 0 })}
                          disabled={selectedStep.step_number === 1}
                          className="w-16 px-2.5 py-1.5 bg-slate-950 border border-white/10 rounded-xl text-xs text-white text-center disabled:opacity-50 disabled:cursor-not-allowed outline-none"
                          placeholder="Days"
                        />
                        <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider font-mono">
                          {selectedStep.step_number === 1 ? 'days (immediate)' : 'days delay'}
                        </span>
                      </div>
                    </div>

                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-505">Email Subject Template</label>
                      <input 
                        type="text" 
                        value={selectedStep.subject_template} 
                        onChange={(e) => setSelectedStep({ ...selectedStep, subject_template: e.target.value })} 
                        className="w-full px-3.5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-xs text-white outline-none focus:border-[#BCA1F7] transition"
                      />
                    </div>

                    <div className="grid gap-4 lg:grid-cols-2">
                      <div className="flex flex-col gap-1">
                        <label className="text-[10px] font-bold uppercase tracking-wider text-slate-505">Plain Text Template Body</label>
                        <textarea 
                          value={selectedStep.text_template} 
                          onChange={(e) => setSelectedStep({ ...selectedStep, text_template: e.target.value })} 
                          rows="16" 
                          className="w-full px-3.5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-[11px] font-mono text-white outline-none focus:border-[#BCA1F7] transition leading-relaxed"
                        />
                      </div>
                      <div className="flex flex-col gap-1">
                        <label className="text-[10px] font-bold uppercase tracking-wider text-slate-550">HTML Template Body (Optional)</label>
                        <textarea 
                          value={selectedStep.html_template} 
                          onChange={(e) => setSelectedStep({ ...selectedStep, html_template: e.target.value })} 
                          rows="16" 
                          className="w-full px-3.5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-[11px] font-mono text-white outline-none focus:border-[#BCA1F7] transition leading-relaxed"
                          placeholder="<p>Write raw HTML parameters...</p>"
                        />
                      </div>
                    </div>

                    <div className="flex justify-end gap-3 pt-2 text-xs">
                      <div className="flex gap-2 mr-auto font-mono text-[9px] font-bold uppercase tracking-wider">
                        <button onClick={() => usePreset('job')} className="rounded-xl border border-white/5 bg-white/5 px-3.5 py-2 hover:bg-white/10 transition cursor-pointer text-slate-200">Job Preset</button>
                        <button onClick={() => usePreset('sales')} className="rounded-xl border border-white/5 bg-white/5 px-3.5 py-2 hover:bg-white/10 transition cursor-pointer text-slate-200">Sales Preset</button>
                      </div>
                      <button 
                        onClick={() => saveSelectedStep()} 
                        className="bg-[#BCA1F7] text-slate-950 font-bold px-5 py-2.5 rounded-xl border border-black/10 transition cursor-pointer flex items-center gap-1"
                      >
                        <Save className="h-4 w-4" /> Save Step Templates
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="h-[450px] flex flex-col items-center justify-center text-center p-8">
                    <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-3xl bg-slate-800 border border-white/5 text-slate-400">
                      <FileText className="h-7 w-7" />
                    </div>
                    <h4 className="text-base font-extrabold text-white">No Step Selected</h4>
                    <p className="mt-2 max-w-sm text-xs text-slate-400 leading-normal">
                      Select a sequence step from the list on the left, or click "+ Add Step" to build your campaign drip sequence stages.
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            🔲 SCREEN: SHIELD & APIS TAB
            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
        {currentTab === 'auth' && (
          <div className="space-y-6">
            <div className="mb-4">
              <h3 className="text-2xl font-serif text-slate-955 font-bold">APIs & Integrations Configuration</h3>
              <p className="text-xs text-slate-505 mt-0.5">Configure Gmail OAuth scopes and Gemini AI model API keys securely.</p>
            </div>

            <div className="grid gap-6 xl:grid-cols-[1.1fr_.9fr]">
              <div className="bg-[#0D0D10] text-slate-200 rounded-[32px] p-6 border border-white/5 shadow-md flex flex-col justify-between">
                <div>
                  <h4 className="text-sm font-bold uppercase tracking-wider text-white mb-4 flex items-between justify-between">
                    <span>Google OAuth Gmail Sign In</span>
                    <span className="text-[10px] font-mono tracking-widest uppercase font-bold text-[#BCA1F7] bg-[#BCA1F7]/10 border border-[#BCA1F7]/20 px-3 py-1 rounded-full">
                      {config.auth_status}
                    </span>
                  </h4>
                  <p className="text-xs text-slate-400 leading-relaxed mb-6">
                    AutoReach uses the official Google Gmail APIs to authenticate sending commands. Click connect below to authorize Gmail sending permission securely through Google's single sign-on system.
                  </p>

                  <div className="space-y-4">
                    <div className="bg-white/5 border border-white/5 flex gap-3.5 rounded-2xl p-4">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-[#BCA1F7]/10 border border-[#BCA1F7]/20 text-[#BCA1F7] font-bold text-xs">1</span>
                      <div>
                        <p className="text-xs font-bold text-white">Official Gmail Redirect authorization</p>
                        <p className="text-[11px] text-slate-400 mt-0.5">Authorize Gmail sending scopes to permit the server to send bulk drafts directly from your mailbox.</p>
                      </div>
                    </div>
                    <div className="bg-white/5 border border-white/5 flex gap-3.5 rounded-2xl p-4">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-[#BCA1F7]/10 border border-[#BCA1F7]/20 text-[#BCA1F7] font-bold text-xs">2</span>
                      <div>
                        <p className="text-xs font-bold text-white">Unlimited background jobs</p>
                        <p className="text-[11px] text-slate-400 mt-0.5">Campaign worker threads maintain execution even while your laptop browser is closed.</p>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="mt-8 flex flex-wrap gap-3">
                  <a 
                    href="/api/auth/google" 
                    className="bg-[#BCA1F7] text-slate-950 font-bold px-6 py-2.5 rounded-xl text-xs uppercase tracking-widest glowing-btn-accent border border-black/10 transition flex items-center gap-1.5"
                  >
                    <ShieldCheck className="h-4 w-4 shrink-0" />
                    <span>{config.token_ready ? 'Reconnect Gmail' : 'Connect Gmail Account'}</span>
                  </a>
                </div>

                {/* Connected Inboxes */}
                <div className="mt-8 pt-6 border-t border-white/5">
                  <h5 className="text-[11px] font-bold uppercase tracking-wider text-slate-505 mb-4 flex items-center gap-2">
                    <Shield className="h-4 w-4 text-[#BCA1F7]" /> Connected Inboxes (Inbox Shield)
                  </h5>
                  <div className="space-y-3">
                    {(config.tokens || []).map(token => (
                      <div key={token.id} className="flex items-center justify-between p-3.5 rounded-2xl bg-white/5 border border-white/5 hover:border-[#BCA1F7]/30 transition">
                        <div className="flex-1 min-w-0 pr-3">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-xs font-bold truncate text-white font-mono">{token.email}</span>
                            <span className={`text-[9px] font-mono font-bold px-2 py-0.5 rounded-full ${
                              token.status === 'reauth_required' 
                                ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20 animate-pulse' 
                                : (token.active ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-slate-850 text-slate-405 border border-slate-750')
                            }`}>
                              {token.status === 'reauth_required' ? 'Quarantined (Reauth Required)' : (token.active ? 'Active' : 'Inactive')}
                            </span>
                          </div>
                          <div className="mt-2.5">
                            <div className="flex justify-between text-[9px] text-slate-405 font-mono font-bold mb-1">
                              <span>Daily Limit Progress</span>
                              <span>{token.daily_sent_count} / 50 sent</span>
                            </div>
                            <div className="h-1.5 overflow-hidden rounded-full bg-slate-805 border border-white/5">
                              <div className="h-full rounded-full bg-[#BCA1F7] transition-all duration-300" style={{ width: `${Math.min((token.daily_sent_count / 50) * 100, 100)}%` }} />
                            </div>
                          </div>
                        </div>
                        <button 
                          onClick={() => disconnectInbox(token.id)} 
                          className="text-xs text-rose-400 hover:text-rose-305 font-semibold px-3 py-1.5 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/10 hover:border-rose-500/20 transition shrink-0 cursor-pointer"
                        >
                          Disconnect
                        </button>
                      </div>
                    ))}
                    {(!config.tokens || config.tokens.length === 0) && (
                      <p className="text-slate-500 text-xs text-center py-4">No email inboxes connected. Connect your Google account to start sending campaigns.</p>
                    )}
                  </div>
                </div>
              </div>

              {/* Gemini settings */}
              <div className="space-y-6">
                <div className="bg-[#0D0D10] text-slate-200 rounded-[32px] p-6 border border-white/5 shadow-md space-y-4">
                  <h4 className="text-sm font-bold uppercase tracking-wider text-white flex items-center justify-between">
                    <span>Gemini AI Pro Personalization</span>
                    <span className={`text-[9px] font-mono font-bold uppercase border px-2 py-0.5 rounded-full ${
                      settings.personalize_enabled ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/20' : 'bg-slate-800 text-slate-400 border-white/10'
                    }`}>
                      {settings.personalize_enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </h4>

                  <div className="space-y-3.5">
                    <label className="flex items-center justify-between rounded-2xl border border-white/5 bg-white/5 p-4 cursor-pointer hover:bg-white/10 transition">
                      <span>
                        <b className="text-xs text-white">Generic Template Sending</b><br/>
                        <span className="text-[10px] text-slate-400">Sends unmodified Jinja templates. Available for all tiers.</span>
                      </span>
                      <input 
                        type="radio" 
                        name="personalization_toggle" 
                        checked={!settings.personalize_enabled} 
                        onChange={() => { setSettings({ ...settings, personalize_enabled: false }); saveSettings(); }}
                        className="cursor-pointer accent-[#BCA1F7]"
                      />
                    </label>

                    <label className={`flex items-center justify-between rounded-2xl border p-4 cursor-pointer transition ${
                      status.user_tier === 'pro' 
                        ? 'border-emerald-500/20 bg-emerald-500/5 hover:bg-emerald-500/10' 
                        : 'border-white/5 opacity-40 cursor-not-allowed'
                    }`}>
                      <span>
                        <b className="text-xs text-emerald-400">Gemini AI Personalization (PRO Only)</b><br/>
                        <span className="text-[10px] text-slate-300">Generates unique subjects/bodies matching sheet contexts.</span>
                      </span>
                      <input 
                        type="radio" 
                        name="personalization_toggle" 
                        disabled={status.user_tier !== 'pro'} 
                        checked={settings.personalize_enabled} 
                        onChange={() => { setSettings({ ...settings, personalize_enabled: true }); saveSettings(); }}
                        className="cursor-pointer accent-emerald-500"
                      />
                    </label>
                  </div>

                  <div className="space-y-4 pt-2">
                    <div className="flex flex-col gap-1">
                      <label className="text-[9px] font-mono font-bold uppercase tracking-wider text-slate-505">Gemini API Key</label>
                      <input 
                        type="password" 
                        value={settings.gemini_api_key} 
                        onChange={(e) => setSettings({ ...settings, gemini_api_key: e.target.value })}
                        className="w-full px-3.5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-xs text-white placeholder-slate-500 outline-none focus:border-[#BCA1F7] transition"
                        placeholder="AI Studio Key (Defaults to Server Key)"
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-[9px] font-mono font-bold uppercase tracking-wider text-slate-505">Gemini LLM Model</label>
                      <input 
                        type="text" 
                        value={settings.personalization_model} 
                        onChange={(e) => setSettings({ ...settings, personalization_model: e.target.value })}
                        className="w-full px-3.5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-xs text-white outline-none focus:border-[#BCA1F7] transition"
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-[9px] font-mono font-bold uppercase tracking-wider text-slate-505">Custom Rewriting Prompt Instructions</label>
                      <textarea 
                        value={settings.personalization_prompt} 
                        onChange={(e) => setSettings({ ...settings, personalization_prompt: e.target.value })}
                        rows="4" 
                        className="w-full px-3.5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-[11px] font-mono text-white outline-none focus:border-[#BCA1F7] transition"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-2.5 pt-2 text-xs">
                    <div>
                      <label className="text-[9px] font-mono font-bold uppercase tracking-wider text-slate-505 block mb-1">Batch Limit</label>
                      <input 
                        type="number" 
                        value={settings.batch_size} 
                        onChange={(e) => setSettings({ ...settings, batch_size: parseInt(e.target.value) || 0 })}
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-xl text-white outline-none text-center"
                      />
                    </div>
                    <div>
                      <label className="text-[9px] font-mono font-bold uppercase tracking-wider text-slate-505 block mb-1">Min Sleep</label>
                      <input 
                        type="number" 
                        value={settings.sleep_min} 
                        onChange={(e) => setSettings({ ...settings, sleep_min: parseInt(e.target.value) || 0 })}
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-xl text-white outline-none text-center"
                      />
                    </div>
                    <div>
                      <label className="text-[9px] font-mono font-bold uppercase tracking-wider text-slate-550 block mb-1">Max Sleep</label>
                      <input 
                        type="number" 
                        value={settings.sleep_max} 
                        onChange={(e) => setSettings({ ...settings, sleep_max: parseInt(e.target.value) || 0 })}
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-xl text-white outline-none text-center"
                      />
                    </div>
                  </div>

                  <button 
                    onClick={() => saveSettings()} 
                    className="w-full bg-[#BCA1F7] text-slate-950 font-bold py-2.5 rounded-xl text-xs uppercase tracking-widest glowing-btn-accent border border-black/10 transition cursor-pointer"
                  >
                    Save Settings
                  </button>
                </div>

                {/* DNS checks */}
                <div className="bg-[#0D0D10] text-slate-200 rounded-[32px] p-6 border border-white/5 shadow-md space-y-4">
                  <h4 className="text-sm font-bold uppercase tracking-wider text-white">Domain DNS Validation Checker</h4>
                  <p className="text-xs text-slate-400 leading-relaxed">Ensure SPF, DKIM, and DMARC settings match Google requirements to avoid high spam rates.</p>
                  
                  <div className="flex gap-2">
                    <input 
                      type="text" 
                      value={dnsCheckedDomain} 
                      onChange={(e) => setDnsCheckedDomain(e.target.value)}
                      className="flex-1 px-3.5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-xs text-white placeholder-slate-500 outline-none focus:border-[#BCA1F7] transition"
                      placeholder="example.com"
                    />
                    <button 
                      onClick={runDnsCheck} 
                      disabled={dnsChecking || !dnsCheckedDomain}
                      className="bg-[#BCA1F7] text-slate-950 font-bold px-4 rounded-xl text-xs uppercase tracking-widest disabled:opacity-40 transition cursor-pointer flex items-center justify-center shrink-0"
                    >
                      {dnsChecking ? <RefreshCw className="h-4 w-4 animate-spin" /> : 'Check'}
                    </button>
                  </div>

                  {dnsResult && (
                    <div className="bg-white/5 rounded-2xl p-4 border border-white/5 space-y-3.5 text-xs text-left font-sans">
                      <div className="flex items-center justify-between border-b border-white/5 pb-2 text-[10px] uppercase font-mono font-bold">
                        <span>DNS Check Result</span>
                        <span className={dnsResult.overall_pass ? 'text-emerald-400' : 'text-rose-400'}>
                          {dnsResult.overall_pass ? 'Pass' : 'Failed'}
                        </span>
                      </div>
                      
                      <div className="space-y-2">
                        {['spf', 'dkim', 'dmarc'].map(k => {
                          const r = dnsResult[k];
                          if (!r) return null;
                          return (
                            <div key={k} className="flex flex-col gap-1 border-b border-white/[0.03] pb-2 last:border-b-0 last:pb-0">
                              <div className="flex items-center justify-between text-[11px]">
                                <span className="font-bold uppercase tracking-wider">{k.toUpperCase()} Record</span>
                                <span className={r.valid ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                                  {r.valid ? 'Valid' : 'Invalid'}
                                </span>
                              </div>
                              {r.value && <p className="font-mono text-[9px] text-slate-400 break-all bg-black/40 p-1.5 rounded mt-1">{r.value}</p>}
                              {!r.valid && r.fix && (
                                <div className="mt-1.5 p-2 rounded bg-rose-500/10 border border-rose-500/15 text-[10px]">
                                  <p className="text-rose-300 font-bold uppercase tracking-wider text-[8px] font-mono">Suggested Fix Action:</p>
                                  <p className="text-slate-300 font-mono mt-0.5 select-text break-all">{r.fix}</p>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

      </main>

      {/* Toast Alert */}
      <AnimatePresence>
        {toast.show && (
          <motion.div 
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="fixed bottom-6 right-6 z-50 rounded-2xl border px-5 py-3.5 text-xs uppercase tracking-wider font-mono font-bold shadow-2xl bg-[#0D0D10] text-[#BCA1F7] border-[#BCA1F7]/30 flex items-center gap-2"
          >
            <Info className="h-4 w-4" />
            <span>{toast.message}</span>
          </motion.div>
        )}
      </AnimatePresence>

    </div>
  );
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 🌟 MAIN EXPORT APPLICATION
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
export default function App() {
  const [currentPath, setCurrentPath] = useState(window.location.pathname);
  const [tickerDismissed, setTickerDismissed] = useState(false);
  const [activeTab, setActiveTab] = useState("Developers");
  const [taglines] = useState(CONFIG.TAGLINES);
  const [taglineIndex, setTaglineIndex] = useState(0);
  const [customApiKey, setCustomApiKey] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState("");
  const [apiKeyExpanded, setApiKeyExpanded] = useState(false);
  const [activeMenu, setActiveMenu] = useState(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [wpmCount, setWpmCount] = useState(0);

  // Router listener for back/forward buttons
  useEffect(() => {
    const handlePopState = () => {
      setCurrentPath(window.location.pathname);
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const navigate = (path) => {
    window.history.pushState({}, "", path);
    setCurrentPath(path);
  };

  // Intercept all local <a> link clicks for reload-free SPA navigation
  useEffect(() => {
    const handleLinkClick = (e) => {
      const target = e.target.closest('a');
      if (target && target.getAttribute('href') && target.getAttribute('href').startsWith('/')) {
        const href = target.getAttribute('href');
        // Exclude specific native endpoints
        if (href === '/logout' || href.startsWith('/api/')) return;
        e.preventDefault();
        navigate(href);
      }
    };
    document.addEventListener('click', handleLinkClick);
    return () => document.removeEventListener('click', handleLinkClick);
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      setTaglineIndex((prev) => (prev + 1) % taglines.length);
    }, 2800);
    return () => clearInterval(interval);
  }, [taglines]);

  useEffect(() => {
    let start = 0;
    const end = 220;
    const totalDuration = 2000;
    const incrementTime = Math.floor(totalDuration / end);
    const timer = setInterval(() => {
      start += 2;
      if (start >= end) {
        setWpmCount(end);
        clearInterval(timer);
      } else {
        setWpmCount(start);
      }
    }, incrementTime);
    return () => clearInterval(timer);
  }, []);

  const generateAITaglines = async () => {
    if (!customApiKey) {
      setAiError("Please enter an Anthropic API Key first.");
      return;
    }
    setAiLoading(true);
    setAiError("");

    try {
      const response = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": customApiKey,
          "anthropic-version": "2023-06-01",
          "dangerously-allow-browser": "true"
        },
        body: JSON.stringify({
          model: "claude-3-5-sonnet-20241022",
          max_tokens: 300,
          system: "Generate 10 short brand slogans (3-6 words) for AutoReach-AI. Return ONLY valid JSON array of strings.",
          messages: [{ role: "user", content: "Generate now." }]
        })
      });

      const data = await response.json();
      if (!response.ok) throw new Error(data.error?.message || "Failed API call.");
      const text = data.content?.[0]?.text || "";
      const parsed = JSON.parse(text.trim());
      if (Array.isArray(parsed) && parsed.length > 0) {
        setApiKeyExpanded(false);
      } else {
        throw new Error("Invalid array.");
      }
    } catch (err) {
      setAiError(err.message || "CORS block or invalid key.");
    } finally {
      setAiLoading(false);
    }
  };

  const NAV_DROPDOWNS = {
    Product: [
      { title: "Inbox Rotation", desc: "Scale sending limits using multiple connected addresses." },
      { title: "Gemini Scrambler", desc: "Unique MIME restructuring to bypass spam filters." },
      { title: "Delivery Shield", desc: "Automated list unsubscribes and SPF/DKIM validation." }
    ],
    "Use Cases": [
      { title: "Inbox Rotation", desc: "Scale sending limits using multiple connected addresses." },
      { title: "Gemini Scrambler", desc: "Unique MIME restructuring to bypass spam filters." },
      { title: "Delivery Shield", desc: "Automated list unsubscribes and SPF/DKIM validation." }
    ],
    Resources: [
      { title: "API Specs", desc: "Connect the campaign engine directly with CRM apps." },
      { title: "Compliance Guide", desc: "Gmail security, Razorpay mandates, and legal layout." }
    ]
  };

  // Route selectors
  if (currentPath === "/login") {
    return <LoginView navigate={navigate} />;
  }
  if (currentPath === "/signup") {
    return <SignupView navigate={navigate} />;
  }
  if (currentPath === "/privacy" || currentPath === "/terms" || currentPath === "/refund-policy" || currentPath === "/contact") {
    return <LegalView path={currentPath} navigate={navigate} />;
  }
  if (currentPath.startsWith("/unsubscribe/")) {
    const token = currentPath.split('/').pop();
    return <UnsubscribeView token={token} navigate={navigate} />;
  }
  if (currentPath === "/dashboard") {
    return <DashboardView navigate={navigate} />;
  }

  // Fallback: original landing page layout
  return (
    <div className="relative min-h-screen bg-[#FAF8F5] text-slate-900 selection:bg-[#BCA1F7]/30 selection:text-slate-955 font-sans">
      
      {/* SVG Noise Overlay */}
      <div className="grain-overlay opacity-[0.03] pointer-events-none fixed inset-0 z-50">
        <svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" className="h-full w-full">
          <filter id="noise">
            <feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="4" stitchTiles="stitch" />
            <feColorMatrix type="linear" values="0 0 0 0 0   0 0 0 0 0   0 0 0 0 0  0 0 0 0.05 0" />
          </filter>
          <rect width="100%" height="100%" filter="url(#noise)" />
        </svg>
      </div>

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          🔲 ANNOUNCEMENT BANNER
          ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      {!tickerDismissed && (
        <div className="relative z-50 flex h-9 w-full items-center justify-between border-b border-black/5 bg-[#121212] px-4 overflow-hidden text-white">
          <div className="flex w-full items-center justify-center">
            <div className="flex w-full overflow-hidden text-xs font-semibold tracking-wide text-slate-300 font-sans">
              <div className="flex animate-infinite-scroll-left whitespace-nowrap gap-16 py-1">
                <span>🚀 AutoReach-AI v2.0 is live with PostgreSQL pooling —</span>
                <span>✨ Auto-pause campaign if Gmail spam rates cross 0.15% —</span>
                <span>🎉 17/17 verified E2E deployment tests fully passing —</span>
                <span>🚀 AutoReach-AI v2.0 is live with PostgreSQL pooling —</span>
              </div>
            </div>
          </div>
          <button 
            onClick={() => setTickerDismissed(true)}
            className="absolute right-3 flex h-5 w-5 items-center justify-center rounded-md hover:bg-white/10 transition text-slate-400 hover:text-white cursor-pointer"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      )}

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          🔲 NAVBAR
          ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      <header className="sticky top-0 z-40 w-full border-b border-black/5 bg-[#FAF8F5]/85 backdrop-blur-md transition-all duration-300">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          
          <div className="flex items-center gap-2 cursor-pointer" onClick={() => navigate('/')}>
            <div className="flex h-9 w-9 items-center justify-center rounded-2xl bg-slate-900 text-white shadow-[0_0_12px_rgba(0,0,0,0.15)]">
              <Sparkles className="h-4.5 w-4.5 text-[#BCA1F7]" />
            </div>
            <span className="text-lg font-bold tracking-tight text-slate-955 font-serif">Flow</span>
          </div>

          <nav className="hidden md:flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
            {Object.keys(NAV_DROPDOWNS).map((item) => (
              <div 
                key={item} 
                className="relative"
                onMouseEnter={() => setActiveMenu(item)}
                onMouseLeave={() => setActiveMenu(null)}
              >
                <button className="flex items-center gap-1 px-3.5 py-1.5 rounded-full hover:text-slate-900 hover:bg-black/5 transition duration-250 cursor-pointer">
                  {item} <ChevronDown className="h-3 w-3" />
                </button>

                <AnimatePresence>
                  {activeMenu === item && (
                    <motion.div 
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: 8 }}
                      transition={{ duration: 0.15 }}
                      className="absolute left-1/2 -translate-x-1/2 top-full pt-3 w-80 z-50"
                    >
                      <div className="bg-[#FAF8F5] rounded-2xl p-4 shadow-2xl border border-black/10">
                        <div className="space-y-2">
                          {NAV_DROPDOWNS[item].map((link, idx) => (
                            <div key={idx} className="flex gap-3 p-2.5 rounded-xl hover:bg-black/5 transition group cursor-pointer text-left">
                              <div>
                                <h5 className="text-[10px] font-bold text-slate-900 uppercase tracking-wider font-mono">{link.title}</h5>
                                <p className="text-[10px] text-slate-500 mt-0.5 leading-normal">{link.desc}</p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            ))}
            <a href="#pricing" className="px-3.5 py-1.5 rounded-full hover:text-slate-900 hover:bg-black/5 transition duration-250">Pricing</a>
          </nav>

          <div className="hidden md:flex items-center gap-4">
            <a href="/login" className="text-xs uppercase tracking-wider font-bold text-slate-500 hover:text-slate-955 transition">Log in</a>
            <motion.a 
              href="/signup" 
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.97 }}
              className="inline-flex items-center justify-center rounded-xl bg-slate-955 text-white px-5 py-2.5 text-xs font-bold shadow-lg border border-black/10"
            >
              Get Started Free
            </motion.a>
          </div>

          <button 
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="flex md:hidden h-9 w-9 items-center justify-center rounded-xl border border-black/5 hover:bg-black/5 transition text-slate-800"
          >
            {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>

        <AnimatePresence>
          {mobileMenuOpen && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="md:hidden border-t border-black/5 bg-[#FAF8F5] overflow-hidden"
            >
              <div className="p-6 space-y-4 flex flex-col text-slate-600 text-xs font-bold uppercase tracking-wider">
                <a href="#product" className="hover:text-slate-900 transition">Product</a>
                <a href="#usecases" className="hover:text-slate-900 transition">Use Cases</a>
                <a href="#pricing" className="hover:text-slate-900 transition">Pricing</a>
                <div className="border-t border-black/5 pt-4 flex flex-col gap-3">
                  <a href="/login" className="text-center py-2 rounded-xl hover:bg-black/5 transition">Log in</a>
                  <a href="/signup" className="text-center bg-slate-950 text-white py-3 rounded-xl">Get Started Free</a>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </header>

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          🔲 SECTION 1: HERO SECTION (WARM CREAM)
          ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      <section id="hero" className="relative mx-auto flex min-h-[calc(100vh-76px)] max-w-6xl flex-col items-center justify-center px-6 py-16 text-center overflow-hidden z-10">
        
        {/* Curved Moving Text overlay */}
        <CurvedTextPath />

        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
          className="flex flex-col items-center justify-center w-full z-10 space-y-8"
        >
          {/* Main Display Headline */}
          <h1 className="font-serif text-6xl font-normal tracking-tight text-slate-955 sm:text-8xl md:text-9xl leading-[1.05] drop-shadow-sm max-w-4xl">
            {CONFIG.HERO_HEADLINE}
          </h1>

          {/* Subheading */}
          <p className="max-w-2xl text-slate-600 text-sm sm:text-base leading-relaxed font-sans font-medium px-4">
            {CONFIG.HERO_SUBHEADLINE}
          </p>

          {/* Centered Voice Wave Interactive widget */}
          <div className="py-4 flex justify-center">
            <VoiceWaveButton />
          </div>

          {/* Lavender/Violet Action Button */}
          <div className="flex flex-col sm:flex-row items-center gap-4 pt-2">
            <motion.a 
              href="/signup" 
              whileHover={{ scale: 1.04, boxShadow: '0 0 24px rgba(188, 161, 247, 0.5)' }}
              whileTap={{ scale: 0.97 }}
              className="inline-flex items-center justify-center rounded-2xl bg-[#BCA1F7] text-slate-950 px-8 py-3.5 text-xs font-extrabold shadow-md border border-slate-955/10 cursor-pointer"
            >
              Download for macOS
            </motion.a>
            <span className="text-[10px] font-mono font-bold tracking-widest text-slate-400 uppercase">Available on Mac, Windows, iPhone, Android</span>
          </div>
        </motion.div>
      </section>

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          🔲 SECTION 2: SHOWCASE ACCORDION (DARK PANEL)
          ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      <section id="showcase" className="mx-auto max-w-6xl px-4 py-8">
        <div className="bg-[#0D0D10] text-slate-100 rounded-[40px] px-8 py-20 border border-white/5 shadow-2xl relative overflow-hidden flex flex-col items-center">
          <div className="absolute inset-0 bg-gradient-to-b from-[#BCA1F7]/5 to-transparent pointer-events-none" />
          
          <div className="text-center max-w-xl mx-auto space-y-4 relative z-10 mb-12">
            {/* Device chips */}
            <div className="flex items-center justify-center gap-2 text-[10px] font-mono font-bold tracking-widest text-slate-500 uppercase">
              <span className="bg-white/5 border border-white/10 px-3 py-1 rounded-full text-slate-200">Mac</span>
              <span>Windows</span>
              <span>iPhone</span>
              <span>Android</span>
            </div>
            <h2 className="font-serif text-3xl font-normal text-white sm:text-5xl tracking-tight leading-tight">
              Write faster in all your apps, on any device
            </h2>
            <p className="text-xs text-slate-400 leading-relaxed font-sans max-w-md mx-auto">
              Seamless speech-to-text in every application on your phone or computer.
            </p>
          </div>

          {/* Curved app icons ribbon sliding */}
          <CurvedIconMarquee />

          {/* Central Interactive Mockup */}
          <div className="relative z-10 mt-8 w-full flex justify-center">
            <InteractiveMockup />
          </div>

          {/* Action button inside Dark section */}
          <div className="mt-12 relative z-10">
            <motion.a
              href="/signup"
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.97 }}
              className="inline-flex items-center justify-center rounded-xl bg-white text-slate-950 px-6 py-3 text-xs font-bold border border-white/20 shadow-md cursor-pointer"
            >
              Watch in action
            </motion.a>
          </div>
        </div>
      </section>

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          🔲 SECTION 3: COMPOSITE BRAND RIBBON
          ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      <section className="py-8 bg-[#0F5A47] text-white border-y border-white/5 overflow-hidden faded-marquee-container flex items-center h-14">
        <div className="flex w-[200%] overflow-hidden">
          <div className="flex animate-infinite-scroll-left whitespace-nowrap gap-16 text-slate-200 font-mono text-[10px] font-bold uppercase tracking-widest">
            <span>Used by professionals everywhere to speed up their thoughts :</span>
            <span>MERCURY</span>
            <span>VERCEL</span>
            <span>REPLIT</span>
            <span>NUULY</span>
            <span>WARP</span>
            <span>RIVIAN</span>
            <span>NOTION</span>
            <span>SUBSTACK</span>
            <span>AMAZON</span>
            <span>STRAVA</span>
            <span>NVIDIA</span>
            <span>LOVABLE</span>
          </div>
        </div>
      </section>

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          🔲 SECTION 4: 4X FASTER COMPARISON (LIGHT CREAM)
          ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      <section id="comparison" className="mx-auto max-w-6xl px-6 py-32 text-center">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          viewport={{ once: true }}
          className="space-y-16"
        >
          <div className="max-w-xl mx-auto space-y-4">
            <h2 className="font-serif text-5xl font-normal text-slate-955 sm:text-7xl tracking-tight leading-tight">
              4x faster than typing
            </h2>
            <p className="text-xs text-slate-600 font-medium max-w-md mx-auto leading-relaxed">
              Voice that finally works is here. Flow lets you create, code, message, and write at the speed of thought, 4x faster than your keyboard.
            </p>
          </div>

          <div className="grid gap-8 md:grid-cols-2 max-w-3xl mx-auto">
            {/* Keyboard Speed */}
            <div className="bg-[#FAF8F5] border border-black/5 rounded-[32px] p-8 flex flex-col justify-between min-h-[220px] text-left shadow-sm">
              <span className="text-[10px] font-mono tracking-widest text-slate-400 uppercase font-bold">Standard Keyboard</span>
              <div className="mt-6 space-y-2">
                <h4 className="text-sm font-bold text-slate-500 font-mono uppercase">Keyboard Speed</h4>
                <p className="font-serif text-5xl font-normal text-slate-500">45 <span className="text-lg">wpm</span></p>
              </div>
              <div className="w-full bg-slate-200 h-1.5 rounded-full overflow-hidden mt-6">
                <div className="bg-slate-400 h-full w-[20%]" />
              </div>
            </div>

            {/* Flow Speed */}
            <div className="bg-[#FAF8F5] border-2 border-[#BCA1F7] rounded-[32px] p-8 flex flex-col justify-between min-h-[220px] text-left shadow-md relative overflow-hidden">
              <div className="absolute top-0 right-0 h-20 w-20 bg-[#BCA1F7]/20 blur-2xl rounded-full" />
              <span className="text-[10px] font-mono tracking-widest text-[#BCA1F7] uppercase font-extrabold flex items-center gap-1.5">
                <Sparkles className="h-3 w-3" /> Voice Flow
              </span>
              <div className="mt-6 space-y-2">
                <h4 className="text-sm font-bold text-slate-955 font-mono uppercase">Speech Dictation</h4>
                <p className="font-serif text-6xl font-normal text-slate-955">
                  {wpmCount} <span className="text-lg text-slate-600">wpm</span>
                </p>
              </div>
              <div className="w-full bg-slate-200 h-1.5 rounded-full overflow-hidden mt-6">
                <motion.div 
                  initial={{ width: 0 }}
                  whileInView={{ width: "100%" }}
                  transition={{ duration: 1.8, ease: "easeOut" }}
                  className="bg-[#BCA1F7] h-full" 
                />
              </div>
            </div>
          </div>
        </motion.div>
      </section>

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          🔲 SECTION 5: WORKFLOW TAB SWITCHER (DARK PANEL)
          ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      <section id="workflows" className="mx-auto max-w-6xl px-4 py-8">
        <div className="bg-[#0D0D10] text-slate-100 rounded-[40px] px-8 py-20 border border-white/5 shadow-2xl relative overflow-hidden">
          <div className="max-w-2xl mx-auto text-center space-y-4 mb-12">
            <h2 className="font-serif text-3xl font-normal text-white sm:text-5xl tracking-tight">
              Made for the way <span className="italic text-[#BCA1F7]">you</span> work
            </h2>
            <p className="text-xs text-slate-400 font-sans max-w-xs mx-auto leading-relaxed">
              Select your workflow to see Flow's templates and speed outputs in action.
            </p>
          </div>

          {/* Workflow Tabs Row */}
          <div className="flex justify-center overflow-x-auto pb-4 border-b border-white/5">
            <div className="flex flex-wrap gap-2 justify-center max-w-2xl">
              {CONFIG.USE_CASES.map((useCase) => (
                <button
                  key={useCase.role}
                  onClick={() => setActiveTab(useCase.role)}
                  className={`px-4 py-1.5 text-[10px] font-mono tracking-wider uppercase rounded-full border transition duration-300 cursor-pointer ${
                    activeTab === useCase.role 
                      ? 'bg-[#BCA1F7] text-slate-900 border-[#BCA1F7] shadow-[0_0_12px_rgba(188,161,247,0.4)]' 
                      : 'border-white/10 text-slate-400 hover:text-white hover:border-white/20 hover:bg-white/5'
                  }`}
                >
                  {useCase.role}
                </button>
              ))}
            </div>
          </div>

          {/* Workflow Active tab content */}
          <div className="mt-12 min-h-[380px] flex items-center justify-center">
            <AnimatePresence mode="wait">
              {CONFIG.USE_CASES.map((useCase) => useCase.role === activeTab && (
                <motion.div 
                  key={useCase.role}
                  initial={{ opacity: 0, y: 15 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -15 }}
                  transition={{ duration: 0.3 }}
                  className="grid gap-12 lg:grid-cols-[1fr_1.20fr] items-center w-full relative z-10"
                >
                  {/* Left block */}
                  <div className="space-y-6 text-left">
                    <span className="font-serif italic text-2xl text-[#BCA1F7]">{useCase.flow}</span>
                    <p className="text-slate-400 text-xs leading-relaxed">{useCase.desc}</p>
                    <div className="pt-2 flex items-center gap-4">
                      <motion.a 
                        href="/signup" 
                        whileHover={{ scale: 1.04 }}
                        whileTap={{ scale: 0.97 }}
                        className="inline-flex items-center justify-center rounded-xl bg-[#BCA1F7] text-slate-900 px-5 py-2.5 text-[10px] font-mono uppercase tracking-widest font-extrabold shadow-md cursor-pointer"
                      >
                        {useCase.cta}
                      </motion.a>
                    </div>
                  </div>

                  {/* Right mockup */}
                  <div className="relative rounded-2xl border border-white/5 overflow-hidden shadow-2xl bg-black/40 p-2">
                    <img 
                      src={useCase.image} 
                      alt={useCase.role}
                      className="w-full h-64 object-cover rounded-xl opacity-80"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-[#0D0D10]/60 to-transparent" />
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>
      </section>

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          🔲 SECTION 6: FOOTER
          ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      <footer className="border-t border-black/5 bg-[#FAF8F5] py-16 text-slate-600">
        <div className="mx-auto max-w-6xl px-6 grid gap-10 md:grid-cols-2 lg:grid-cols-5 text-left">
          
          <div className="lg:col-span-2 space-y-4">
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-2xl bg-slate-900 text-white shadow-sm">
                <Sparkles className="h-4 w-4 text-[#BCA1F7]" />
              </div>
              <span className="text-base font-bold text-slate-955 tracking-tight font-serif">Flow</span>
            </div>
            <p className="text-xs text-slate-505 max-w-xs leading-normal">
              Autonomous AI outreach pipeline configured with deliverability guards, Gemini engines, and multi-inbox rotation.
            </p>
          </div>

          {Object.keys(CONFIG.FOOTER_LINKS).map((col) => (
            <div key={col} className="space-y-4">
              <h5 className="text-[10px] font-mono font-bold uppercase tracking-wider text-slate-400">{col}</h5>
              <ul className="space-y-2 text-xs text-slate-550 font-sans font-medium">
                {CONFIG.FOOTER_LINKS[col].map((link, idx) => (
                  <li key={idx}>
                    <a href={link.href} className="hover:text-[#BCA1F7] transition duration-200">{link.label}</a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mx-auto max-w-6xl px-6 border-t border-black/5 mt-12 pt-8 flex flex-col sm:flex-row items-center justify-between text-[10px] text-slate-400 font-mono font-bold uppercase tracking-wider">
          <div>© {new Date().getFullYear()} {CONFIG.APP_NAME}. All rights reserved.</div>
          <div className="flex gap-4 mt-4 sm:mt-0">
            <a href="/privacy" className="hover:text-slate-600 transition">Privacy</a>
            <a href="/terms" className="hover:text-slate-600 transition">Terms</a>
            <a href="/refund-policy" className="hover:text-slate-600 transition">Refunds</a>
          </div>
        </div>
      </footer>

    </div>
  );
}

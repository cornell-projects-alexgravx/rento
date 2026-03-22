import { useState, useRef, useEffect } from 'react'
import {
  Bell, ChevronDown, Moon, Sun, LogOut,
  Zap, Home, Settings,
} from 'lucide-react'
import { useStore } from '../../store/useStore'
import { Button } from '../ui/button'
import { cn } from '../../lib/utils'
import { useNavigate } from 'react-router-dom'

export function Navbar() {
  const {
    darkMode, toggleDarkMode,
    agentStatus, notifications, markAllRead, unreadCount,
    topTab, setTopTab,
    setPrefModal,
  } = useStore()

  const [notifOpen, setNotifOpen] = useState(false)
  const [userOpen, setUserOpen] = useState(false)
  const notifRef = useRef<HTMLDivElement>(null)
  const userRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) setNotifOpen(false)
      if (userRef.current && !userRef.current.contains(e.target as Node)) setUserOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <header className="h-14 flex items-center justify-between px-5 border-b border-[rgba(1,2,5,0.10)] bg-white dark:border-[rgba(255,215,0,0.15)] dark:bg-[#0F0F0F] shrink-0 z-30">
      {/* Logo */}
      <div
        className="flex items-center gap-2 cursor-pointer shrink-0"
        onClick={() => navigate('/dashboard')}
      >
        <div className="w-7 h-7 rounded-md bg-indigo-600 flex items-center justify-center">
          <Home size={15} className="text-white" />
        </div>
        <span className="font-bold text-base text-[#010205] dark:text-white tracking-tight" style={{ fontFamily: "'Sakana', sans-serif" }}>
          RentAgent<span className="text-indigo-400"> AI</span>
        </span>
      </div>

      {/* Center — top-level tabs */}
      <nav className="flex items-center gap-1 absolute left-1/2 -translate-x-1/2">
        {(['match', 'agent'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setTopTab(tab)}
            className={cn(
              'px-4 py-1.5 rounded-full text-sm font-medium transition-all duration-150 capitalize',
              topTab === tab
                ? 'bg-[#010205] text-white dark:bg-yellow-400 dark:text-black shadow-sm'
                : 'text-[#6B6B6B] hover:text-[#010205] hover:bg-[#F0F0F1] dark:text-yellow-400/60 dark:hover:text-yellow-400 dark:hover:bg-[#1A1A1A]'
            )}
          >
            {tab === 'match' ? '🏠 Match' : '🤖 Agent Log'}
          </button>
        ))}
      </nav>

      {/* Right side */}
      <div className="flex items-center gap-1.5 shrink-0">
        {/* Agent status pill */}
        <div
          className={cn(
            'flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium',
            agentStatus.isRunning
              ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
              : 'bg-[#F0F0F1] text-[#6B6B6B] dark:bg-[#1A1A1A] dark:text-yellow-400/60'
          )}
        >
          <span className={cn('w-1.5 h-1.5 rounded-full', agentStatus.isRunning ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400')} />
          <Zap size={11} />
          {agentStatus.isRunning ? 'Running' : 'Paused'}
        </div>

        {/* Dark mode */}
        <Button variant="ghost" size="icon" onClick={toggleDarkMode} className="w-8 h-8">
          {darkMode ? <Sun size={16} /> : <Moon size={16} />}
        </Button>

        {/* Notifications */}
        <div className="relative" ref={notifRef}>
          <Button
            variant="ghost" size="icon"
            onClick={() => setNotifOpen(v => !v)}
            className="relative w-8 h-8"
          >
            <Bell size={16} />
            {unreadCount > 0 && (
              <span className="absolute top-1 right-1 w-3.5 h-3.5 rounded-full bg-red-500 text-white text-[9px] font-bold flex items-center justify-center">
                {unreadCount}
              </span>
            )}
          </Button>

          {notifOpen && (
            <div className="absolute right-0 top-10 w-[360px] bg-white dark:bg-[#0F0F0F] rounded-xl shadow-xl border border-[rgba(1,2,5,0.10)] dark:border-[rgba(255,215,0,0.15)] z-50 overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2.5 border-b border-[rgba(1,2,5,0.10)] dark:border-[rgba(255,215,0,0.15)]">
                <h3 className="font-semibold text-sm text-[#010205] dark:text-white">Notifications</h3>
                <button onClick={markAllRead} className="text-xs text-[#6A5CFF] dark:text-yellow-400 hover:underline">
                  Mark all read
                </button>
              </div>
              <div className="max-h-80 overflow-y-auto scrollbar-thin">
                {notifications.map((n) => (
                  <div
                    key={n.id}
                    className={cn(
                      'px-4 py-3 border-b border-[rgba(1,2,5,0.08)] dark:border-[rgba(255,215,0,0.08)] last:border-0',
                      !n.read && 'bg-[#F0F0F1] dark:bg-yellow-400/5'
                    )}
                  >
                    <div className="flex items-start gap-2">
                      {!n.read && <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-[#6A5CFF] dark:bg-yellow-400 shrink-0" />}
                      <div className={!n.read ? '' : 'ml-3.5'}>
                        <p className="text-xs font-medium text-[#010205] dark:text-white">{n.title}</p>
                        <p className="text-xs text-[#6B6B6B] dark:text-yellow-400/60 mt-0.5">{n.message}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Profile / User menu */}
        <div className="relative" ref={userRef}>
          <button
            onClick={() => setUserOpen(v => !v)}
            className="flex items-center gap-1.5 pl-1 pr-2 py-1 rounded-lg hover:bg-[#F0F0F1] dark:hover:bg-[#1A1A1A] transition-colors"
          >
            <div className="w-7 h-7 rounded-full bg-[#EBEBEC] dark:bg-[#242424] flex items-center justify-center text-[#6A5CFF] dark:text-yellow-400 font-semibold text-xs">
              AK
            </div>
            <ChevronDown size={13} className="text-[#9A9A9A] dark:text-yellow-400/40" />
          </button>

          {userOpen && (
            <div className="absolute right-0 top-10 w-56 bg-white dark:bg-[#0F0F0F] rounded-xl shadow-xl border border-[rgba(1,2,5,0.10)] dark:border-[rgba(255,215,0,0.15)] z-50 overflow-hidden">
              {/* User info */}
              <div className="px-4 py-3 border-b border-[rgba(1,2,5,0.10)] dark:border-[rgba(255,215,0,0.15)]">
                <p className="text-sm font-semibold text-[#010205] dark:text-white">Alex Kim</p>
                <p className="text-xs text-[#6B6B6B] dark:text-yellow-400/60">alex@example.com</p>
              </div>

              {/* Preferences — 3 tabs */}
              <div className="py-1">
                <p className="px-4 pt-2 pb-1 text-[10px] font-semibold text-[#9A9A9A] dark:text-yellow-400/40 uppercase tracking-wider">
                  Preferences
                </p>
                {([
                  { tab: 'housing', label: '🏠 Housing' },
                  { tab: 'negotiation', label: '🤝 Negotiation' },
                  { tab: 'notifications', label: '🔔 Notifications' },
                ] as const).map(({ tab, label }) => (
                  <button
                    key={tab}
                    onClick={() => { setPrefModal(true, tab); setUserOpen(false) }}
                    className="w-full flex items-center gap-2 px-4 py-2 text-sm text-[#4A4A4A] dark:text-yellow-400/70 hover:bg-[#F0F0F1] dark:hover:bg-[#1A1A1A] transition-colors"
                  >
                    <Settings size={13} className="text-[#9A9A9A] dark:text-yellow-400/40" />
                    {label}
                  </button>
                ))}
              </div>

              <div className="border-t border-[rgba(1,2,5,0.10)] dark:border-[rgba(255,215,0,0.15)] py-1">
                <button
                  onClick={() => navigate('/onboarding')}
                  className="w-full flex items-center gap-2 px-4 py-2 text-sm text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                >
                  <LogOut size={13} />
                  Sign out
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}

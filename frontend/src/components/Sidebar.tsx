import { useState, useEffect } from 'react'
import { NavLink } from 'react-router-dom'
import { LayoutDashboard, TableProperties, FileText, Database, ChevronLeft, ChevronRight } from 'lucide-react'

const nav = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/results', icon: TableProperties, label: 'Results' },
  { to: '/audit', icon: FileText, label: 'AI Audit Report' },
]

export default function Sidebar() {
  const [isCollapsed, setIsCollapsed] = useState(() => {
    const saved = localStorage.getItem('sidebar-collapsed')
    return saved === 'true'
  })

  useEffect(() => {
    localStorage.setItem('sidebar-collapsed', String(isCollapsed))
  }, [isCollapsed])

  return (
    <aside className={`bg-slate-900 border-r border-slate-800 flex flex-col h-full shrink-0 shadow-lg select-none transition-all duration-300 ease-in-out ${isCollapsed ? 'w-[70px]' : 'w-60'}`}>
      {/* Brand Header */}
      <div className={`px-4 py-6 border-b border-slate-800/80 flex items-center justify-between gap-2 overflow-hidden ${isCollapsed ? 'flex-col' : 'flex-row'}`}>
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-500/10 rounded-lg border border-blue-500/20 shrink-0">
            <Database className="text-blue-400 animate-pulse" size={18} />
          </div>
          {!isCollapsed && (
            <div className="transition-opacity duration-300 whitespace-nowrap">
              <p className="text-slate-100 font-bold text-sm tracking-tight leading-tight">Validata</p>
              <p className="text-slate-500 text-[9px] font-bold tracking-wider uppercase leading-none mt-1.5">Validation Engine</p>
            </div>
          )}
        </div>

        <button
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="p-1.5 rounded-md hover:bg-slate-800/85 text-slate-400 hover:text-slate-200 transition-colors"
          title={isCollapsed ? 'Expand Sidebar' : 'Collapse Sidebar'}
        >
          {isCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
        </button>
      </div>

      {/* Nav List */}
      <nav className="flex-1 px-3 py-6 space-y-1.5">
        {nav.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            title={isCollapsed ? label : undefined}
            className={({ isActive }) =>
              `flex items-center rounded-lg text-xs font-semibold tracking-tight transition-all duration-200 ${
                isCollapsed ? 'justify-center p-2.5' : 'gap-3 px-3 py-2.5'
              } ${
                isActive
                  ? 'bg-blue-600/10 text-blue-400 border border-blue-500/25 shadow-sm shadow-blue-500/5'
                  : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200 border border-transparent'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <Icon size={14} className={isActive ? 'text-blue-400' : 'text-slate-400'} />
                {!isCollapsed && (
                  <span className="transition-opacity duration-300 whitespace-nowrap">{label}</span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer / System Health */}
      <div className="p-4 border-t border-slate-800/80 bg-slate-950/20">
        <div className={`flex items-center justify-between ${isCollapsed ? 'flex-col gap-2' : 'flex-row px-2'}`}>
          <div className="flex items-center gap-2" title="System Live">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-ping absolute duration-1000"></span>
            <span className="relative h-1.5 w-1.5 rounded-full bg-emerald-500 shrink-0"></span>
            {!isCollapsed && (
              <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider transition-opacity duration-300">Engine Live</span>
            )}
          </div>
          {!isCollapsed && (
            <span className="text-[10px] text-slate-600 font-semibold font-mono transition-opacity duration-300">v1.0.0</span>
          )}
        </div>
      </div>
    </aside>
  )
}

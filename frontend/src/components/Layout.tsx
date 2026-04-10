import { ClipboardList, FileText, LayoutDashboard } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'
import { useHealth } from '@/hooks/useWorkflows'

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/specs', label: 'Specs', icon: FileText, end: false },
  { to: '/audit', label: 'Audit Trail', icon: ClipboardList, end: false },
] as const

export function Layout() {
  const { data: health } = useHealth()

  return (
    <div className="flex h-screen bg-slate-50">
      {/* Sidebar */}
      <aside className="flex w-56 flex-col" style={{ backgroundColor: '#0f172a' }}>
        {/* Brand */}
        <div className="flex items-center gap-2 border-b border-slate-700 px-5 py-4">
          <span className="text-lg font-semibold tracking-tight text-white">CDDE</span>
          <span className="text-xs text-slate-400">Clinical Derivation</span>
        </div>

        {/* Nav */}
        <nav className="flex-1 space-y-1 px-3 py-4">
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-slate-700 text-white'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-white'
                }`
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Health indicator */}
        <div className="border-t border-slate-700 px-5 py-3">
          <div className="flex items-center gap-2">
            <span
              className={`h-2 w-2 rounded-full ${
                health?.status === 'ok' ? 'bg-emerald-400' : 'bg-red-400'
              }`}
            />
            <span className="text-xs text-slate-400">
              {health ? `API ${health.version}` : 'Connecting...'}
            </span>
          </div>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}

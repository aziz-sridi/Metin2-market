import { NavLink } from 'react-router-dom'
import { useTheme } from '../lib/theme.js'

function NavItem({ to, end, children }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        [
          'inline-flex items-center rounded-md px-3 py-2 text-sm font-medium',
          isActive
            ? 'bg-slate-200 text-slate-900 dark:bg-slate-800 dark:text-white'
            : 'text-slate-700 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-900 dark:hover:text-slate-100',
        ].join(' ')
      }
    >
      {children}
    </NavLink>
  )
}

export default function Layout({ children }) {
  const { isDark, toggleTheme } = useTheme()

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
        <div className="mx-auto max-w-none px-4 py-3">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="min-w-0 flex items-center gap-3">
              <div className="h-10 w-10 rounded-md border border-slate-200 bg-white p-1 dark:border-slate-800 dark:bg-slate-900/40">
                <img
                  src="/metin2-mark.svg"
                  alt="Metin2"
                  className="h-full w-full"
                  loading="eager"
                />
              </div>

              <div className="min-w-0">
                <div className="text-sm font-semibold tracking-wide text-slate-900 dark:text-slate-100">Metin2 Warehouse</div>
                <div className="text-xs text-slate-600 dark:text-slate-400">Market intelligence & alerts</div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <nav className="flex flex-wrap gap-2">
                <NavItem to="/" end>
                  Home
                </NavItem>
                <NavItem to="/alerts">Alerts</NavItem>
                <NavItem to="/price-history">Price history</NavItem>
                <NavItem to="/equipment">Equipment</NavItem>
                <NavItem to="/deals">Deals</NavItem>
              </nav>

              <button
                type="button"
                onClick={toggleTheme}
                role="switch"
                aria-checked={isDark}
                aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
                className="ml-auto inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-900 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2 focus:ring-offset-slate-50 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:hover:bg-slate-900 dark:focus:ring-offset-slate-950"
              >
                <span className="text-sm">{isDark ? 'Dark' : 'Light'}</span>
                <span
                  className={
                    [
                      'relative inline-flex h-6 w-11 flex-shrink-0 rounded-full',
                      isDark ? 'bg-slate-700' : 'bg-slate-200',
                    ].join(' ')
                  }
                >
                  <span
                    className={
                      [
                        'inline-block h-5 w-5 translate-x-0 transform rounded-full bg-white',
                        isDark ? 'translate-x-5' : 'translate-x-1',
                      ].join(' ')
                    }
                  />
                </span>
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-none px-4 py-6">
        {children}
      </main>
    </div>
  )
}

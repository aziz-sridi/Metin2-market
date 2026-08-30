import { NavLink } from 'react-router-dom'

function NavItem({ to, end, children }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        [
          'nav-link',
          isActive
            ? 'nav-link-active'
            : '',
        ].join(' ')
      }
    >
      {children}
    </NavLink>
  )
}

export default function Layout({ children }) {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-inner">
          <NavLink className="wordmark" to="/" aria-label="Metin2 Market home">
            Metin2 Market
          </NavLink>

          <nav className="app-nav" aria-label="Primary navigation">
            <NavItem to="/" end>Overview</NavItem>
            <NavItem to="/alerts">Alerts</NavItem>
            <NavItem to="/price-history">History</NavItem>
            <NavItem to="/equipment">Equipment</NavItem>
            <NavItem to="/deals">Deals</NavItem>
          </nav>
        </div>
      </header>

      <main className="app-main">
        {children}
      </main>
    </div>
  )
}

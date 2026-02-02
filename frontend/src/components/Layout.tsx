import { Link, useLocation } from 'react-router-dom'
import { FileText, Search, Home } from 'lucide-react'
import clsx from 'clsx'

interface LayoutProps {
  children: React.ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation()

  const navItems = [
    { path: '/', label: 'Documents', icon: Home },
    { path: '/search', label: 'Search', icon: Search },
  ]

  return (
    <div className="min-h-screen flex flex-col bg-cp-dark text-cp-text font-mono">
      <header className="bg-cp-card/80 backdrop-blur-md border-b border-cp-neon-purple/30 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Link to="/" className="flex items-center gap-2 group">
              <FileText className="h-8 w-8 text-cp-neon-green group-hover:drop-shadow-[0_0_8px_rgba(57,255,20,0.8)] transition-all" />
              <span className="text-xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-cp-neon-green to-cp-neon-blue tracking-tighter">
                CYBER.PIPELINE
              </span>
            </Link>
            <nav className="flex gap-4">
              {navItems.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  className={clsx(
                    'flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-all duration-300',
                    location.pathname === item.path
                      ? 'bg-cp-neon-purple/20 text-cp-neon-green border border-cp-neon-purple/50 shadow-[0_0_10px_rgba(176,38,255,0.3)]'
                      : 'text-cp-text-muted hover:text-cp-neon-blue hover:bg-white/5'
                  )}
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
        </div>
      </header>
      <main className="flex-1">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {children}
        </div>
      </main>
      <footer className="bg-cp-card border-t border-cp-neon-purple/30 py-4 mt-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <p className="text-center text-sm text-cp-text-muted">
            CYBER.VECTOR_DB // SYS.V.1.0.0
          </p>
        </div>
      </footer>
    </div>
  )
}

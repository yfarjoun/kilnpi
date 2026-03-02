import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { Dashboard } from './pages/Dashboard';
import { Monitor } from './pages/Monitor';
import { Programs } from './pages/Programs';
import { History } from './pages/History';
import { Settings } from './pages/Settings';

const navItems = [
  { path: '/', label: 'Dashboard' },
  { path: '/monitor', label: 'Monitor' },
  { path: '/programs', label: 'Programs' },
  { path: '/history', label: 'History' },
  { path: '/settings', label: 'Settings' },
];

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-900 text-white">
        <nav className="bg-gray-800 border-b border-gray-700">
          <div className="max-w-6xl mx-auto px-4 flex items-center h-14 gap-6">
            <span className="font-bold text-lg tracking-tight">Kiln Controller</span>
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === '/'}
                className={({ isActive }) =>
                  `text-sm hover:text-white transition-colors ${
                    isActive ? 'text-white font-medium' : 'text-gray-400'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </div>
        </nav>
        <main className="max-w-6xl mx-auto px-4 py-6">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/monitor" element={<Monitor />} />
            <Route path="/programs" element={<Programs />} />
            <Route path="/history" element={<History />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

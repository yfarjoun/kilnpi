import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { Dashboard } from './pages/Dashboard';
import { Monitor } from './pages/Monitor';
import { Programs } from './pages/Programs';
import { History } from './pages/History';
import { Statistics } from './pages/Statistics';
import { Settings } from './pages/Settings';
import { PiStatus } from './pages/PiStatus';
import { useTheme } from './hooks/useTheme';

const navItems = [
  { path: '/', label: 'Dashboard' },
  { path: '/monitor', label: 'Monitor' },
  { path: '/programs', label: 'Programs' },
  { path: '/history', label: 'History' },
  { path: '/statistics', label: 'Statistics' },
  { path: '/pi', label: 'Pi' },
  { path: '/settings', label: 'Settings' },
];

export default function App() {
  const { theme, toggle } = useTheme();

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-50 text-gray-900 dark:bg-gray-900 dark:text-white">
        <nav className="bg-white border-b border-gray-200 dark:bg-gray-800 dark:border-gray-700">
          <div className="max-w-6xl mx-auto px-4 flex items-center h-14 gap-6">
            <span className="font-bold text-lg tracking-tight">Kiln Controller</span>
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === '/'}
                className={({ isActive }) =>
                  `text-sm hover:text-gray-900 dark:hover:text-white transition-colors ${
                    isActive ? 'text-gray-900 dark:text-white font-medium' : 'text-gray-500 dark:text-gray-400'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
            <button
              onClick={toggle}
              className="ml-auto px-2 py-1 rounded text-sm text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white transition-colors"
              title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {theme === 'dark' ? '\u2600\uFE0F' : '\uD83C\uDF19'}
            </button>
          </div>
        </nav>
        <main className="max-w-6xl mx-auto px-4 py-6">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/monitor" element={<Monitor />} />
            <Route path="/programs" element={<Programs />} />
            <Route path="/history" element={<History />} />
            <Route path="/statistics" element={<Statistics />} />
            <Route path="/pi" element={<PiStatus />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

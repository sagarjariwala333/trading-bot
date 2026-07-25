import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useTheme } from '../hooks/useTheme';

function Navbar() {
  const { isDark, toggleTheme } = useTheme();

  return (
    <nav className="fixed top-0 left-0 right-0 h-[64px] bg-[#0d1220]/90 dark:bg-[#0d1220]/90 backdrop-blur-md border-b border-white/[0.06] px-6 md:px-8 flex items-center justify-between z-50 transition-colors duration-300">
      <div className="flex items-center gap-3">
        <span className="text-lg font-black tracking-tight bg-gradient-to-r from-blue-400 to-indigo-500 bg-clip-text text-transparent">
          ALGO-HA TRADER
        </span>
        <Badge variant="outline" className="text-blue-400 border-blue-500/25 bg-blue-500/10 text-[10px] tracking-wider">
          Live Engine
        </Badge>
      </div>
      <div className="flex items-center gap-4">
        <Badge variant="outline" className="text-emerald-400 border-emerald-500/20 bg-emerald-500/10 gap-1.5">
          <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />
          System Online
        </Badge>

        <Button
          size="sm"
          onClick={toggleTheme}
          className="bg-slate-700 hover:bg-slate-600 dark:bg-slate-300 dark:hover:bg-slate-200 text-white dark:text-slate-900 font-semibold px-3 py-1.5 h-auto rounded-md transition-all duration-150"
          title={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
        >
          {isDark ? '☀️ Light' : '🌙 Dark'}
        </Button>
      </div>
    </nav>
  );
}

export default Navbar;

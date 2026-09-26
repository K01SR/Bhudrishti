import React, { useEffect, useState } from 'react';
import { KeyRound, UserRound, Loader2, LogIn, ShieldCheck, UserX } from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { fetchDemoAccounts, type DemoAccount } from '../../services/api';
import { Modal, Button } from '../ui';
import { cn } from '../../lib/cn';

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

export const LoginModal: React.FC<Props> = ({ isOpen, onClose }) => {
  const { login, showToast } = useApp();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [demoAccounts, setDemoAccounts] = useState<DemoAccount[]>([]);

  useEffect(() => {
    if (!isOpen) {
      setUsername('');
      setPassword('');
      setError(null);
      setIsLoading(false);
      return;
    }
    fetchDemoAccounts()
      .then(setDemoAccounts)
      .catch(() => setDemoAccounts([]));
  }, [isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const u = username.trim();
    if (!u || !password) {
      setError('Enter both username and password.');
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const user = await login(u, password);
      showToast(`Welcome, ${user.full_name.split(' ')[0]}`);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={
        <span className="flex items-center gap-2">
          <KeyRound className="w-4 h-4 text-accent-strong" />
          Role-wise sign-in
        </span>
      }
      size="sm"
    >
      <form onSubmit={handleSubmit} className="space-y-4" data-testid="login-form">
        <p className="text-xs text-ink-mut -mt-1">
          Sign in with a role account. Demo accounts use password <span className="font-mono font-bold">demo@2026</span>.
        </p>

        <label className="block">
          <span className="text-[11px] font-bold text-ink-soft uppercase tracking-wide">Username</span>
          <div className="mt-1 flex items-center gap-2 border-2 border-ink rounded-lg bg-canvas px-3 focus-within:ring-2 focus-within:ring-accent/30">
            <UserRound className="w-4 h-4 text-ink-mut" />
            <input
              name="username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. district.admin"
              className="w-full py-2.5 bg-transparent text-sm font-semibold text-ink focus:outline-none placeholder:text-ink-faint"
            />
          </div>
        </label>

        <label className="block">
          <span className="text-[11px] font-bold text-ink-soft uppercase tracking-wide">Password</span>
          <div className="mt-1 flex items-center gap-2 border-2 border-ink rounded-lg bg-canvas px-3 focus-within:ring-2 focus-within:ring-accent/30">
            <ShieldCheck className="w-4 h-4 text-ink-mut" />
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="demo@2026"
              className="w-full py-2.5 bg-transparent text-sm font-semibold text-ink focus:outline-none placeholder:text-ink-faint"
            />
          </div>
        </label>

        {error && (
          <div className="text-xs font-semibold text-red-600 bg-red-50 border-2 border-red-100 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        <Button type="submit" variant="primary" className="w-full" disabled={isLoading}>
          {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <LogIn className="w-4 h-4" />}
          {isLoading ? 'Signing in…' : 'Sign in'}
        </Button>

        <button
          type="button"
          onClick={onClose}
          className="flex items-center justify-center gap-1.5 w-full text-xs font-bold text-ink-mut hover:text-ink py-1.5 transition"
        >
          <UserX className="w-3.5 h-3.5" />
          Continue as Public guest
        </button>
      </form>

      {demoAccounts.length > 0 && (
        <div className="mt-2 border-t border-ink pt-3">
          <div className="text-[10px] font-bold text-ink-mut uppercase tracking-wider mb-2">
            Demo role accounts — one-click fill
          </div>
          <div className="grid grid-cols-1 gap-1.5 max-h-56 overflow-y-auto pr-1">
            {demoAccounts.map((acc) => (
              <button
                key={acc.username}
                type="button"
                onClick={() => {
                  setUsername(acc.username);
                  setPassword(acc.password || 'demo@2026');
                  setError(null);
                }}
                className={cn(
                  'text-left px-3 py-2 rounded-lg border-2 text-xs transition',
                  username === acc.username
                    ? 'border-accent/40 bg-accent/10'
                    : 'border-ink hover:bg-canvas'
                )}
              >
                <span className="font-mono font-bold text-ink">{acc.username}</span>
                <span className="block text-[11px] text-ink-mut truncate">
                  {acc.full_name}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </Modal>
  );
};
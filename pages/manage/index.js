import Head from 'next/head';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { useAcademy } from '../../lib/academyStore';
import { ManageCtx } from '../../components/manage/ui';
import Dashboard from '../../components/manage/Dashboard';
import Employees from '../../components/manage/Employees';
import Work from '../../components/manage/Work';
import Leaves from '../../components/manage/Leaves';
import Payroll from '../../components/manage/Payroll';
import Contracts from '../../components/manage/Contracts';
import Settings from '../../components/manage/Settings';

const NAV = [
  { sec: '현황' },
  { key: 'dashboard', label: '대시보드', ico: '📊', C: Dashboard },
  { sec: '인사' },
  { key: 'employees', label: '직원 정보', ico: '👥', C: Employees },
  { key: 'work', label: '근태 관리', ico: '⏰', C: Work },
  { key: 'leaves', label: '휴가 관리', ico: '🏖️', C: Leaves },
  { key: 'payroll', label: '급여 관리', ico: '💰', C: Payroll },
  { key: 'contracts', label: '계약 관리', ico: '📝', C: Contracts },
  { sec: '기타' },
  { key: 'settings', label: '설정 · 백업', ico: '⚙️', C: Settings },
];

export default function ManagePage() {
  const { settings } = useAcademy();
  const [tab, setTab] = useState('dashboard');
  const [params, setParams] = useState(null);
  const [toast, setToast] = useState('');
  const [menuOpen, setMenuOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
    const apply = () => { const h = window.location.hash.slice(1); if (NAV.some((n) => n.key === h)) { setTab(h); setParams(null); } };
    apply();
    window.addEventListener('hashchange', apply);
    return () => window.removeEventListener('hashchange', apply);
  }, []);

  const notify = useCallback((msg) => { setToast(msg); setTimeout(() => setToast(''), 2600); }, []);
  const go = useCallback((key, p = null) => { setTab(key); setParams(p); setMenuOpen(false); if (typeof window !== 'undefined') window.history.replaceState(null, '', '#' + key); window.scrollTo(0, 0); }, []);

  const Active = NAV.find((n) => n.key === tab)?.C || Dashboard;

  return (
    <ManageCtx.Provider value={{ notify, go }}>
      <Head>
        <title>인사 관리 시스템 · {settings.academyName || 'HIQ입시학원'}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      </Head>
      <div className="mg">
        <header className="mg-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <button className="mg-menu-btn" onClick={() => setMenuOpen((v) => !v)} aria-label="메뉴">☰</button>
            <Link href="/manage" className="mg-logo">
              <div className="mg-logo-mark">HIQ</div>
              <div className="mg-logo-text">인사 관리 시스템<span className="mg-logo-sub">{settings.academyName || 'HIQ입시학원'}</span></div>
            </Link>
          </div>
          <div className="mg-header-right">
            {process.env.NEXT_PUBLIC_DESKTOP ? <span className="mg-link" style={{ cursor: 'default' }}>데스크톱</span> : <Link href="/" className="mg-link">지문 분석기 →</Link>}
          </div>
        </header>
        <div className="mg-layout">
          <aside className={`mg-side ${menuOpen ? 'open' : ''}`}>
            <nav className="mg-nav">
              {NAV.map((n, i) => n.sec
                ? <div key={'s' + i} className="mg-nav-sec">{n.sec}</div>
                : <button key={n.key} className={tab === n.key ? 'active' : ''} onClick={() => go(n.key)}><span className="ico">{n.ico}</span>{n.label}</button>)}
            </nav>
          </aside>
          <main className="mg-content" onClick={() => menuOpen && setMenuOpen(false)}>
            {mounted ? <Active params={params} /> : null}
          </main>
        </div>
        {toast && <div className="mg-toast">{toast}</div>}
      </div>
    </ManageCtx.Provider>
  );
}

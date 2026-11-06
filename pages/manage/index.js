import Head from 'next/head';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { useAcademy } from '../../lib/academyStore';
import { ManageCtx } from '../../components/manage/ui';
import Dashboard from '../../components/manage/Dashboard';
import Students from '../../components/manage/Students';
import Classes from '../../components/manage/Classes';
import Teachers from '../../components/manage/Teachers';
import Attendance from '../../components/manage/Attendance';
import Payments from '../../components/manage/Payments';
import Counseling from '../../components/manage/Counseling';
import Settings from '../../components/manage/Settings';

const NAV = [
  { sec: '현황' },
  { key: 'dashboard', label: '대시보드', ico: '📊', C: Dashboard },
  { sec: '학생' },
  { key: 'students', label: '학생 관리', ico: '🎓', C: Students },
  { key: 'attendance', label: '출결 관리', ico: '✅', C: Attendance },
  { key: 'counseling', label: '상담 기록', ico: '💬', C: Counseling },
  { sec: '운영' },
  { key: 'classes', label: '반 · 수업 관리', ico: '🏫', C: Classes },
  { key: 'teachers', label: '강사 관리', ico: '👩‍🏫', C: Teachers },
  { key: 'payments', label: '학원비 수납', ico: '💳', C: Payments },
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
  useEffect(() => { setMounted(true); const h = window.location.hash.slice(1); if (NAV.some((n) => n.key === h)) setTab(h); }, []);

  const notify = useCallback((msg) => { setToast(msg); setTimeout(() => setToast(''), 2600); }, []);
  const go = useCallback((key, p = null) => { setTab(key); setParams(p); setMenuOpen(false); if (typeof window !== 'undefined') window.history.replaceState(null, '', '#' + key); window.scrollTo(0, 0); }, []);

  const Active = NAV.find((n) => n.key === tab)?.C || Dashboard;

  return (
    <ManageCtx.Provider value={{ notify, go }}>
      <Head>
        <title>학원 관리 시스템 · {settings.academyName || 'HIQ입시학원'}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      </Head>
      <div className="mg">
        <header className="mg-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <button className="mg-menu-btn" onClick={() => setMenuOpen((v) => !v)} aria-label="메뉴">☰</button>
            <Link href="/manage" className="mg-logo">
              <div className="mg-logo-mark">HIQ</div>
              <div className="mg-logo-text">학원 관리 시스템<span className="mg-logo-sub">{settings.academyName || 'HIQ입시학원'}</span></div>
            </Link>
          </div>
          <div className="mg-header-right">
            <Link href="/" className="mg-link">지문 분석기 →</Link>
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

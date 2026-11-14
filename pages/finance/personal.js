import { useEffect, useMemo, useState } from 'react';
import FinanceLayout, { useToast } from '../../components/finance/Layout';
import DataTab from '../../components/finance/DataTab';
import TrendChart from '../../components/finance/TrendChart';
import { StatTile, MeterList, MonthNav, Empty, copy } from '../../components/finance/ui';
import { useLocalState } from '../../lib/finance/store';
import { PERSONAL_CATEGORIES, PERSONAL_NON_SPEND, isIncomeCategory } from '../../lib/finance/rules';
import { summarize, monthlyTotals } from '../../lib/finance/categorize';
import { detectRecurring, INTERVAL_LABEL } from '../../lib/finance/recurring';
import { won, pct, thisMonth, monthLabel, lastNMonths, shiftMonth, uid, todayISO, wonShort } from '../../lib/finance/format';
import { aiCall } from '../../lib/finance/ai';

const INITIAL = { txs: [], memory: {}, budgets: {}, goals: [], subs: {} };
const TABS = [['report', '월 리포트'], ['budget', '예산'], ['goals', '저축 목표'], ['subs', '구독·고정지출'], ['data', '거래내역']];
const EXPENSE_CATS = PERSONAL_CATEGORIES.filter((c) => c !== '수입' && !PERSONAL_NON_SPEND.includes(c));
const isIncome = (c) => isIncomeCategory('personal', c);

// 이체·송금, 카드대금(카드 내역과 중복), 저축·투자 이체는 소비가 아니므로 지출 집계에서 제외
const spendTxs = (txs) => txs.filter((t) => !PERSONAL_NON_SPEND.includes(t.category));

export default function PersonalPage() {
  const [state, setState, loaded] = useLocalState('hiq.fin.personal.v1', INITIAL);
  const [tab, setTab] = useState('report');
  const [month, setMonth] = useState(thisMonth());
  const [setToast, toastEl] = useToast();

  // 이번 달 거래가 없으면 가장 최근 거래가 있는 달을 기본으로
  useEffect(() => {
    if (!loaded) return;
    const txs = state.txs || [];
    if (!txs.length || txs.some((t) => t.month === thisMonth())) return;
    setMonth(txs.map((t) => t.month).sort().pop());
  }, [loaded]); // eslint-disable-line react-hooks/exhaustive-deps

  const overBudget = useMemo(() => {
    const s = summarize(spendTxs(state.txs || []), month, isIncome);
    return s.expense.filter((r) => state.budgets?.[r.name] && r.value > state.budgets[r.name]).length;
  }, [state.txs, state.budgets, month]);

  if (!loaded) return <FinanceLayout title="개인"><div className="note">불러오는 중...</div></FinanceLayout>;

  return (
    <FinanceLayout title="개인">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: 10, marginBottom: 14 }}>
        <div>
          <h1 style={{ fontSize: 20, color: 'var(--navy)', fontWeight: 800 }}>👤 개인 전담 재무 비서</h1>
          <p className="note">지출 분류 · 예산 · 저축 목표 · 구독 점검</p>
        </div>
        {(tab === 'report' || tab === 'budget') && <MonthNav month={month} onChange={setMonth} />}
      </div>
      <div className="subtabs">
        {TABS.map(([k, label]) => (
          <div key={k} className={`subtab${tab === k ? ' active' : ''}`} onClick={() => setTab(k)}>
            {label}
            {k === 'budget' && overBudget > 0 && <span className="cnt">{overBudget}</span>}
            {k === 'data' && (state.txs || []).filter((t) => !t.category).length > 0 && <span className="cnt">!</span>}
          </div>
        ))}
      </div>

      {tab === 'report' && <Report state={state} month={month} setToast={setToast} />}
      {tab === 'budget' && <Budget state={state} setState={setState} month={month} />}
      {tab === 'goals' && <Goals state={state} setState={setState} setToast={setToast} />}
      {tab === 'subs' && <Subs state={state} setState={setState} setToast={setToast} />}
      {tab === 'data' && (
        <DataTab domain="personal" state={state} setState={setState} categories={PERSONAL_CATEGORIES} setToast={setToast}
          hint="주거래 은행 입출금 내역과 카드 이용내역을 함께 올리면 가장 정확합니다." />
      )}
      {toastEl}
    </FinanceLayout>
  );
}

/* ───────────── 월 리포트 ───────────── */
function Report({ state, month, setToast }) {
  const [ai, setAi] = useState('');
  const [busy, setBusy] = useState(false);
  const txs = spendTxs(state.txs || []);
  const cur = useMemo(() => summarize(txs, month, isIncome), [txs, month]);
  const prev = useMemo(() => summarize(txs, shiftMonth(month, -1), isIncome), [txs, month]);
  const trend = useMemo(() => monthlyTotals(txs, lastNMonths(6, month)), [txs, month]);
  const prevMap = Object.fromEntries(prev.expense.map((r) => [r.name, r.value]));
  const changes = cur.expense
    .map((r) => ({ name: r.name, now: r.value, before: prevMap[r.name] || 0, diff: r.value - (prevMap[r.name] || 0) }))
    .concat(prev.expense.filter((r) => !cur.expense.find((c) => c.name === r.name)).map((r) => ({ name: r.name, now: 0, before: r.value, diff: -r.value })))
    .sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff)).slice(0, 5);
  const rows = cur.expense.map((r) => ({ ...r, limit: state.budgets?.[r.name] || 0 }));
  const savingRate = cur.incomeTotal ? Math.round((cur.net / cur.incomeTotal) * 100) : null;
  const savedTransfers = (state.txs || []).filter((t) => t.month === month && t.category === '저축·투자' && t.amount < 0).reduce((a, t) => a - t.amount, 0);
  const recurring = useMemo(() => detectRecurring(state.txs || []).filter((r) => r.active), [state.txs]);
  const fixedMonthly = recurring.reduce((a, r) => a + r.monthlyCost, 0);

  const askAI = async () => {
    setBusy(true);
    try {
      const summary = [
        `대상 월: ${monthLabel(month)}`,
        `수입 ${won(cur.incomeTotal)} (전월 ${won(prev.incomeTotal)}), 지출 ${won(cur.expenseTotal)} (전월 ${won(prev.expenseTotal)}), 순저축 ${won(cur.net)}${savingRate !== null ? ` (저축률 ${savingRate}%)` : ''}`,
        `지출 카테고리: ${cur.expense.map((r) => `${r.name} ${won(r.value)}${state.budgets?.[r.name] ? ` (예산 ${won(state.budgets[r.name])})` : ''}`).join(', ') || '없음'}`,
        `전월 대비 변화 TOP: ${changes.map((c) => `${c.name} ${won(c.diff, { plus: true })}`).join(', ') || '없음'}`,
        `반복 결제(구독·고정): ${recurring.map((r) => `${r.name} ${won(r.amount)}/${INTERVAL_LABEL[r.interval]}`).join(', ') || '없음'} (월 환산 ${won(fixedMonthly)})`,
        `저축 목표: ${(state.goals || []).map((g) => `${g.name} ${won(g.current)}/${won(g.target)}${g.deadline ? ` (${g.deadline}까지)` : ''}`).join(', ') || '없음'}`,
        `최근 6개월: ${trend.map((t) => `${t.month} 수입 ${wonShort(t.income)}/지출 ${wonShort(t.expense)}`).join('; ')}`,
      ].join('\n');
      const r = await aiCall('analyze', { domain: 'personal', summary, question: '1) 이번 달 소비 한 줄 평가 2) 가장 효과 큰 절약 포인트 3가지(카테고리·금액·방법) 3) 다음 달 예산 제안(카테고리별 금액) 4) 저축 목표 달성 가능성 코멘트. 숫자로 근거를 대고 짧게.' });
      setAi(r.text);
    } catch (e) { setToast('AI 분석 실패: ' + e.message); }
    setBusy(false);
  };

  if (!(state.txs || []).length) {
    return <div className="card"><Empty>아직 거래내역이 없습니다. <b>거래내역</b> 탭에서 은행·카드 파일을 가져오세요.</Empty></div>;
  }

  return (
    <>
      <div className="grid g4" style={{ marginBottom: 20 }}>
        <StatTile label="수입" value={cur.incomeTotal} tone="pos" delta={cur.incomeTotal - prev.incomeTotal} />
        <StatTile label="지출" value={cur.expenseTotal} delta={cur.expenseTotal - prev.expenseTotal} />
        <StatTile label="순저축" value={cur.net} tone={cur.net < 0 ? 'neg' : 'pos'} delta={cur.net - prev.net} />
        <StatTile label="저축률" raw={savingRate === null ? '-' : `${savingRate}%`} delta={null} />
      </div>
      {savedTransfers > 0 && <div className="banner ok">이번 달 적금·투자 계좌로 이체한 금액 {won(savedTransfers)} — 지출이 아니라 저축으로 분류되어 순저축에 포함됩니다.</div>}
      <div className="card">
        <div className="card-title"><span>최근 6개월 수입·지출</span><small>이체·송금 · 카드대금 · 저축이체 제외</small></div>
        <TrendChart data={trend} />
      </div>
      <div className="grid g2">
        <div className="card">
          <div className="card-title"><span>카테고리별 지출</span><small>{monthLabel(month)} · 검은 선 = 예산</small></div>
          <MeterList rows={rows} />
        </div>
        <div className="card">
          <div className="card-title"><span>전월 대비 변화</span><small>변동 큰 순</small></div>
          {!changes.length ? <Empty>비교할 전월 데이터가 없습니다.</Empty> : (
            <table className="tbl">
              <thead><tr><th>카테고리</th><th className="num">전월</th><th className="num">이번 달</th><th className="num">변화</th></tr></thead>
              <tbody>
                {changes.map((c) => (
                  <tr key={c.name}>
                    <td>{c.name}</td>
                    <td className="num muted">{won(c.before)}</td>
                    <td className="num">{won(c.now)}</td>
                    <td className={`num ${c.diff > 0 ? 'neg' : 'pos'}`}>{won(c.diff, { plus: true })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {fixedMonthly > 0 && <p className="note" style={{ marginTop: 12 }}>고정지출·구독 월 환산 <b>{won(fixedMonthly)}</b> ({recurring.length}건) — 구독 탭에서 점검</p>}
        </div>
      </div>
      <div className="card">
        <div className="card-title">
          <span>AI 절약 제안</span>
          <div className="btn-row">
            {ai && <button className="btn-copy" onClick={() => copy(ai, setToast)}>복사</button>}
            <button className="btn btn-sm btn-primary" disabled={busy} onClick={askAI}>{busy && <span className="spinner" />}{busy ? '분석 중...' : ai ? '다시 분석' : '이번 달 분석 요청'}</button>
          </div>
        </div>
        {ai ? <div className="ai-box">{ai}</div> : <p className="note">카테고리 합계·예산·반복 결제·목표를 바탕으로 절약 포인트와 다음 달 예산을 제안합니다.</p>}
      </div>
    </>
  );
}

/* ───────────── 예산 ───────────── */
function Budget({ state, setState, month }) {
  const txs = spendTxs(state.txs || []);
  const cur = useMemo(() => summarize(txs, month, isIncome), [txs, month]);
  const prev3 = useMemo(() => {
    const months = lastNMonths(3, shiftMonth(month, -1));
    const acc = {};
    months.forEach((m) => summarize(txs, m, isIncome).expense.forEach((r) => { acc[r.name] = (acc[r.name] || 0) + r.value; }));
    return Object.fromEntries(Object.entries(acc).map(([k, v]) => [k, Math.round(v / 3)]));
  }, [txs, month]);
  const spent = Object.fromEntries(cur.expense.map((r) => [r.name, r.value]));
  const budgets = state.budgets || {};
  const setB = (cat, v) => setState((s) => ({ ...s, budgets: { ...(s.budgets || {}), [cat]: Number(v) || 0 } }));
  const totalBudget = Object.values(budgets).reduce((a, b) => a + b, 0);
  const totalSpent = cur.expenseTotal;
  const dayOfMonth = month === thisMonth() ? new Date().getDate() : 31;
  const daysIn = new Date(Number(month.slice(0, 4)), Number(month.slice(5)), 0).getDate();
  const pace = totalBudget ? Math.round((totalBudget * dayOfMonth) / daysIn) : 0;
  const fillFromAvg = () => setState((s) => ({ ...s, budgets: { ...(s.budgets || {}), ...Object.fromEntries(Object.entries(prev3).map(([k, v]) => [k, Math.round(v / 10000) * 10000])) } }));

  return (
    <>
      <div className="grid g4" style={{ marginBottom: 20 }}>
        <StatTile label="월 예산 합계" value={totalBudget} />
        <StatTile label="이번 달 지출" value={totalSpent} tone={totalBudget && totalSpent > totalBudget ? 'neg' : undefined} />
        <StatTile label="남은 예산" value={totalBudget - totalSpent} tone={totalBudget - totalSpent < 0 ? 'neg' : 'pos'} />
        <StatTile label="진도 대비" raw={totalBudget ? `${pct(totalSpent, totalBudget)}% / ${pct(pace, totalBudget)}%` : '-'} />
      </div>
      <div className="card">
        <div className="card-title">
          <span>카테고리별 예산 <small>{monthLabel(month)} 사용 현황</small></span>
          <button className="btn btn-sm btn-ghost" onClick={fillFromAvg} disabled={!Object.keys(prev3).length}>최근 3개월 평균으로 채우기</button>
        </div>
        <p className="note" style={{ marginBottom: 10 }}>진도 대비: 지출 비율 / 오늘까지 쓰는 것이 적정한 비율. 80% 이상은 노란색, 초과는 빨간색으로 표시됩니다.</p>
        <table className="tbl">
          <thead><tr><th>카테고리</th><th className="num">월 예산</th><th className="num">3개월 평균</th><th className="num">사용</th><th style={{ width: '30%' }}>사용률</th><th className="num">남음</th></tr></thead>
          <tbody>
            {EXPENSE_CATS.map((cat) => {
              const b = budgets[cat] || 0, s = spent[cat] || 0;
              const r = b ? s / b : 0;
              const cls = b && r > 1 ? 'over' : b && r >= 0.8 ? 'warn' : '';
              return (
                <tr key={cat}>
                  <td>{cat}</td>
                  <td className="num"><input type="number" step="10000" value={b || ''} placeholder="0" onChange={(e) => setB(cat, e.target.value)} style={{ width: 110, textAlign: 'right' }} /></td>
                  <td className="num muted">{prev3[cat] ? won(prev3[cat]) : '-'}</td>
                  <td className="num">{won(s)}</td>
                  <td>
                    <div className="trk" style={{ height: 10, background: 'var(--graylt)', position: 'relative' }}>
                      <div className={`bar ${cls}`} style={{ position: 'absolute', left: 0, top: 0, height: '100%', width: `${b ? Math.min(100, r * 100) : 0}%`, background: cls === 'over' ? 'var(--status-bad)' : cls === 'warn' ? 'var(--status-warn)' : 'var(--seq-450)', borderRadius: '0 4px 4px 0' }} />
                    </div>
                    {b ? <span className="note">{pct(s, b)}%{r > 1 ? ' · 초과' : ''}</span> : null}
                  </td>
                  <td className={`num ${b && b - s < 0 ? 'neg' : ''}`}>{b ? won(b - s) : '-'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

/* ───────────── 저축 목표 ───────────── */
function Goals({ state, setState, setToast }) {
  const [form, setForm] = useState({ name: '', target: '', current: '', deadline: '' });
  const goals = state.goals || [];
  const add = () => {
    if (!form.name.trim() || !Number(form.target)) { setToast('목표 이름과 금액을 입력하세요.'); return; }
    setState((s) => ({ ...s, goals: [...(s.goals || []), { id: uid(), name: form.name, target: Number(form.target), current: Number(form.current) || 0, deadline: form.deadline, created: todayISO() }] }));
    setForm({ name: '', target: '', current: '', deadline: '' });
  };
  const upd = (id, patch) => setState((s) => ({ ...s, goals: s.goals.map((g) => (g.id === id ? { ...g, ...patch } : g)) }));
  const del = (id) => { if (window.confirm('목표를 삭제할까요?')) setState((s) => ({ ...s, goals: s.goals.filter((g) => g.id !== id) })); };
  const monthsLeft = (deadline) => {
    if (!deadline) return null;
    const [y, m] = deadline.split('-').map(Number);
    const now = new Date();
    return Math.max(0, (y - now.getFullYear()) * 12 + (m - (now.getMonth() + 1)));
  };
  // 최근 3개월 평균 순저축으로 실현 가능성 추정
  const avgNet = useMemo(() => {
    const txs = spendTxs(state.txs || []);
    const ms = lastNMonths(3, shiftMonth(thisMonth(), -1));
    const t = monthlyTotals(txs, ms);
    const n = t.filter((x) => x.income || x.expense).length;
    return n ? Math.round(t.reduce((a, x) => a + x.income - x.expense, 0) / n) : null;
  }, [state.txs]);
  const needTotal = goals.reduce((a, g) => { const ml = monthsLeft(g.deadline); return a + (ml ? Math.max(0, g.target - g.current) / ml : 0); }, 0);

  return (
    <>
      <div className="grid g3" style={{ marginBottom: 20 }}>
        <StatTile label="목표 합계" value={goals.reduce((a, g) => a + g.target, 0)} />
        <StatTile label="매월 필요 저축액" value={Math.round(needTotal)} tone={avgNet !== null && needTotal > avgNet ? 'neg' : undefined} />
        <StatTile label="최근 3개월 평균 순저축" value={avgNet} tone={avgNet < 0 ? 'neg' : 'pos'} raw={avgNet === null ? '데이터 없음' : undefined} />
      </div>
      <div className="card">
        <div className="card-title"><span>저축 목표</span></div>
        {!goals.length ? <Empty>목표를 추가하세요. 기한을 넣으면 매월 필요한 저축액을 계산합니다.</Empty> : (
          <div className="meter-list" style={{ gap: 16 }}>
            {goals.map((g) => {
              const ml = monthsLeft(g.deadline);
              const need = ml ? Math.max(0, g.target - g.current) / ml : null;
              const done = g.current >= g.target;
              return (
                <div key={g.id} style={{ borderBottom: '1px solid var(--graylt)', paddingBottom: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                    <div><b>{g.name}</b> {done && <span className="chip green">달성</span>} <span className="note">{g.deadline ? `${g.deadline}까지 · ${ml}개월 남음` : '기한 없음'}</span></div>
                    <div className="btn-row">
                      <span className="note">현재</span>
                      <input type="number" step="10000" value={g.current} onChange={(e) => upd(g.id, { current: Number(e.target.value) })} style={{ width: 120, textAlign: 'right' }} />
                      <span className="note">/ 목표</span>
                      <input type="number" step="10000" value={g.target} onChange={(e) => upd(g.id, { target: Number(e.target.value) })} style={{ width: 120, textAlign: 'right' }} />
                      <input type="month" value={g.deadline || ''} onChange={(e) => upd(g.id, { deadline: e.target.value })} />
                      <button className="btn btn-sm btn-ghost" onClick={() => del(g.id)}>✕</button>
                    </div>
                  </div>
                  <div className="trk" style={{ height: 10, background: 'var(--graylt)', margin: '8px 0 4px', position: 'relative' }}>
                    <div style={{ position: 'absolute', left: 0, top: 0, height: '100%', width: `${Math.min(100, pct(g.current, g.target))}%`, background: done ? 'var(--status-good)' : 'var(--seq-450)', borderRadius: '0 4px 4px 0' }} />
                  </div>
                  <div className="note">{pct(g.current, g.target)}% 달성 · 남은 금액 {won(Math.max(0, g.target - g.current))}{need !== null && !done ? ` · 매월 ${won(Math.ceil(need))} 필요` : ''}{need !== null && avgNet !== null && !done ? (need > avgNet ? ' · ⚠ 최근 평균 순저축보다 많음' : ' · ✓ 현재 저축 속도로 가능') : ''}</div>
                </div>
              );
            })}
          </div>
        )}
        <div className="grid g4" style={{ marginTop: 16, alignItems: 'end' }}>
          <div className="field"><label className="fl">목표 이름 *</label><input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="비상금 / 여행 / 전세 보증금" /></div>
          <div className="field"><label className="fl">목표 금액 *</label><input type="number" value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })} placeholder="5000000" /></div>
          <div className="field"><label className="fl">현재 모은 금액</label><input type="number" value={form.current} onChange={(e) => setForm({ ...form, current: e.target.value })} placeholder="0" /></div>
          <div className="field"><label className="fl">기한(월)</label><input type="month" value={form.deadline} onChange={(e) => setForm({ ...form, deadline: e.target.value })} /></div>
          <button className="btn btn-primary" onClick={add}>+ 목표 추가</button>
        </div>
      </div>
    </>
  );
}

/* ───────────── 구독·고정지출 ───────────── */
function Subs({ state, setState, setToast }) {
  const items = useMemo(() => detectRecurring(state.txs || []), [state.txs]);
  const subs = state.subs || {};
  const setStatus = (key, status) => setState((s) => ({ ...s, subs: { ...(s.subs || {}), [key]: { status } } }));
  const active = items.filter((i) => i.active && subs[i.key]?.status !== 'cancelled');
  const monthly = active.reduce((a, i) => a + i.monthlyCost, 0);
  const review = active.filter((i) => subs[i.key]?.status === 'review');
  const saving = review.reduce((a, i) => a + i.monthlyCost, 0);

  return (
    <>
      <div className="grid g3" style={{ marginBottom: 20 }}>
        <StatTile label="활성 반복 결제" raw={`${active.length}건`} />
        <StatTile label="월 환산 고정지출" value={monthly} />
        <StatTile label="해지 검토 시 월 절약" value={saving} tone="pos" />
      </div>
      <div className="card">
        <div className="card-title">
          <span>자동 탐지된 반복 결제</span>
          {review.length > 0 && <button className="btn-copy" onClick={() => copy(review.map((i) => `${i.name} ${won(i.amount)}/${INTERVAL_LABEL[i.interval]}`).join('\n'), setToast)}>해지 목록 복사</button>}
        </div>
        <p className="note" style={{ marginBottom: 10 }}>같은 가맹점에서 비슷한 금액이 매주·매월·매년 간격으로 2회 이상 결제된 항목입니다. 2개월 이상 거래내역이 있어야 탐지됩니다. 최근 결제가 없으면 '중단됨'으로 표시합니다.</p>
        {!items.length ? <Empty>반복 결제를 찾지 못했습니다. 거래내역을 2개월 이상 가져오면 탐지됩니다.</Empty> : (
          <div style={{ overflowX: 'auto' }}>
            <table className="tbl">
              <thead><tr><th>가맹점</th><th>카테고리</th><th className="num">결제액</th><th>주기</th><th className="num">월 환산</th><th className="num">횟수</th><th>최근 결제</th><th>상태</th><th>판단</th></tr></thead>
              <tbody>
                {items.map((i) => {
                  const st = subs[i.key]?.status || 'keep';
                  return (
                    <tr key={i.key} style={{ opacity: i.active ? 1 : 0.55 }}>
                      <td>{i.name}</td>
                      <td className="note">{i.category || '-'}</td>
                      <td className="num">{won(i.amount)}</td>
                      <td>{INTERVAL_LABEL[i.interval]}</td>
                      <td className="num">{won(i.monthlyCost)}</td>
                      <td className="num">{i.count}회</td>
                      <td className="note">{i.lastDate}</td>
                      <td>{i.active ? <span className="chip green">활성</span> : <span className="chip gray">중단됨</span>}</td>
                      <td>
                        <select value={st} onChange={(e) => setStatus(i.key, e.target.value)}>
                          <option value="keep">유지</option>
                          <option value="review">해지 검토</option>
                          <option value="cancelled">해지함</option>
                        </select>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

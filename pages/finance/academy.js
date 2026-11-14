import { useEffect, useMemo, useState } from 'react';
import FinanceLayout, { useToast } from '../../components/finance/Layout';
import DataTab from '../../components/finance/DataTab';
import TrendChart from '../../components/finance/TrendChart';
import { StatTile, MeterList, MonthNav, Empty, copy } from '../../components/finance/ui';
import { useLocalState } from '../../lib/finance/store';
import { ACADEMY_CATEGORIES, ACADEMY_NON_PL, isIncomeCategory } from '../../lib/finance/rules';
import { summarize, monthlyTotals } from '../../lib/finance/categorize';
import { won, pct, thisMonth, monthLabel, lastNMonths, shiftMonth, uid, todayISO, daysBetween } from '../../lib/finance/format';
import { calcPay, DEFAULT_RATES } from '../../lib/finance/payroll';
import { buildTaxCalendar, KIND_LABEL } from '../../lib/finance/tax';
import { aiCall } from '../../lib/finance/ai';

const INITIAL = {
  profile: { name: 'HIQ입시학원', halfYearWithholding: false, hasEmployees: true, hasTaxableSales: false, sincere: false },
  txs: [], memory: {},
  students: [], payments: {},
  instructors: [], rates: DEFAULT_RATES,
};

const TABS = [['dash', '월 손익'], ['tuition', '수강료 수납'], ['payroll', '강사 급여'], ['tax', '세무 일정'], ['data', '거래내역']];

export default function AcademyPage() {
  const [state, setState, loaded] = useLocalState('hiq.fin.academy.v1', INITIAL);
  const [tab, setTab] = useState('dash');
  const [month, setMonth] = useState(thisMonth());
  const [setToast, toastEl] = useToast();

  // 이번 달 거래가 없으면 가장 최근 거래가 있는 달을 기본으로
  useEffect(() => {
    if (!loaded) return;
    const txs = state.txs || [];
    if (!txs.length || txs.some((t) => t.month === thisMonth())) return;
    setMonth(txs.map((t) => t.month).sort().pop());
  }, [loaded]); // eslint-disable-line react-hooks/exhaustive-deps
  const isIncome = (c) => isIncomeCategory('academy', c);

  const unpaidCount = useMemo(() => {
    const pm = state.payments?.[month] || {};
    return (state.students || []).filter((s) => s.active !== false && !pm[s.id]?.paid).length;
  }, [state.students, state.payments, month]);

  const upcomingTax = useMemo(() => {
    const y = new Date().getFullYear();
    const all = [...buildTaxCalendar(y, state.profile), ...buildTaxCalendar(y + 1, state.profile)];
    const today = todayISO();
    return all.filter((e) => e.date >= today && daysBetween(today, e.date) <= 14).length;
  }, [state.profile]);

  if (!loaded) return <FinanceLayout title="학원"><div className="note">불러오는 중...</div></FinanceLayout>;

  return (
    <FinanceLayout title="학원">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: 10, marginBottom: 14 }}>
        <div>
          <h1 style={{ fontSize: 20, color: 'var(--navy)', fontWeight: 800 }}>🏫 학원 전담 재무 비서</h1>
          <p className="note">
            <input type="text" value={state.profile.name} onChange={(e) => setState((s) => ({ ...s, profile: { ...s.profile, name: e.target.value } }))} style={{ padding: '2px 6px', fontSize: 12.5, width: 160 }} /> 의 수납·손익·급여·세무를 한 곳에서
          </p>
        </div>
        {tab !== 'tax' && tab !== 'data' && <MonthNav month={month} onChange={setMonth} />}
      </div>

      <div className="subtabs">
        {TABS.map(([k, label]) => (
          <div key={k} className={`subtab${tab === k ? ' active' : ''}`} onClick={() => setTab(k)}>
            {label}
            {k === 'tuition' && unpaidCount > 0 && <span className="cnt">{unpaidCount}</span>}
            {k === 'tax' && upcomingTax > 0 && <span className="cnt">{upcomingTax}</span>}
            {k === 'data' && state.txs.filter((t) => !t.category).length > 0 && <span className="cnt">!</span>}
          </div>
        ))}
      </div>

      {tab === 'dash' && <Dashboard state={state} month={month} isIncome={isIncome} setToast={setToast} />}
      {tab === 'tuition' && <Tuition state={state} setState={setState} month={month} setToast={setToast} />}
      {tab === 'payroll' && <Payroll state={state} setState={setState} month={month} setToast={setToast} />}
      {tab === 'tax' && <TaxCalendar state={state} setState={setState} />}
      {tab === 'data' && (
        <DataTab domain="academy" state={state} setState={setState} categories={ACADEMY_CATEGORIES} setToast={setToast}
          hint="학원 사업용 계좌(수강료 입금 계좌)와 사업자 카드 내역을 올리세요." />
      )}
      {toastEl}
    </FinanceLayout>
  );
}

/* ───────────── 월 손익 ───────────── */
function Dashboard({ state, month, isIncome, setToast }) {
  const [ai, setAi] = useState('');
  const [busy, setBusy] = useState(false);
  // 카드대금·대표자 계좌 이동 등 내부거래는 손익에서 제외 (카드 이용내역을 함께 올리면 지출이 중복되지 않음)
  const txs = useMemo(() => (state.txs || []).filter((t) => !ACADEMY_NON_PL.includes(t.category)), [state.txs]);
  const cur = useMemo(() => summarize(txs, month, isIncome), [txs, month]);
  const prev = useMemo(() => summarize(txs, shiftMonth(month, -1), isIncome), [txs, month]);
  const trend = useMemo(() => monthlyTotals(txs, lastNMonths(6, month)), [txs, month]);
  const pm = state.payments?.[month] || {};
  const active = (state.students || []).filter((s) => s.active !== false);
  const paid = active.filter((s) => pm[s.id]?.paid).length;
  const expectedTuition = active.reduce((a, s) => a + Number(s.fee || 0), 0);

  const askAI = async () => {
    setBusy(true);
    try {
      const lines = [
        `학원명: ${state.profile.name}`, `대상 월: ${monthLabel(month)}`,
        `수입 합계: ${won(cur.incomeTotal)} (전월 ${won(prev.incomeTotal)})`,
        `지출 합계: ${won(cur.expenseTotal)} (전월 ${won(prev.expenseTotal)})`,
        `순이익: ${won(cur.net)} (전월 ${won(prev.net)})`,
        `수입 내역: ${cur.income.map((r) => `${r.name} ${won(r.value)}`).join(', ') || '없음'}`,
        `지출 내역: ${cur.expense.map((r) => `${r.name} ${won(r.value)}`).join(', ') || '없음'}`,
        `전월 지출 내역: ${prev.expense.map((r) => `${r.name} ${won(r.value)}`).join(', ') || '없음'}`,
        active.length ? `등록 학생 ${active.length}명, 수납 ${paid}명, 월 수강료 예정액 ${won(expectedTuition)}` : '',
        `최근 6개월 추이: ${trend.map((t) => `${t.month} 수입 ${won(t.income)}/지출 ${won(t.expense)}`).join('; ')}`,
      ].filter(Boolean).join('\n');
      const r = await aiCall('analyze', { domain: 'academy', summary: lines, question: '원장이 바로 읽을 수 있게: 1) 이번 달 손익 핵심 진단 3가지 2) 전월 대비 눈에 띄는 변화 3) 다음 달 실행할 행동 2~3개 4) 세무상 챙길 점 1가지(세무사 확인 필요 표시).' });
      setAi(r.text);
    } catch (e) { setToast('AI 분석 실패: ' + e.message); }
    setBusy(false);
  };

  if (!(state.txs || []).length) {
    return <div className="card"><Empty>아직 거래내역이 없습니다. <b>거래내역</b> 탭에서 학원 계좌 파일을 가져오세요. 학생을 등록하면 수납률도 함께 표시됩니다.</Empty></div>;
  }

  return (
    <>
      <div className="grid g4" style={{ marginBottom: 20 }}>
        <StatTile label="수입" value={cur.incomeTotal} tone="pos" delta={cur.incomeTotal - prev.incomeTotal} />
        <StatTile label="지출" value={cur.expenseTotal} delta={cur.expenseTotal - prev.expenseTotal} />
        <StatTile label="순이익" value={cur.net} tone={cur.net < 0 ? 'neg' : 'pos'} delta={cur.net - prev.net} />
        <StatTile label="수강료 수납률" raw={active.length ? `${pct(paid, active.length)}%` : '-'} delta={null} />
      </div>
      <div className="card">
        <div className="card-title"><span>최근 6개월 수입·지출</span><small>내부거래·카드대금 제외</small></div>
        <TrendChart data={trend} />
      </div>
      <div className="grid g2">
        <div className="card">
          <div className="card-title"><span>수입 구성</span><small>{monthLabel(month)}</small></div>
          <MeterList rows={cur.income} income />
        </div>
        <div className="card">
          <div className="card-title"><span>지출 구성</span><small>{monthLabel(month)}</small></div>
          <MeterList rows={cur.expense} />
        </div>
      </div>
      <div className="card">
        <div className="card-title">
          <span>AI 재무 코멘트</span>
          <div className="btn-row">
            {ai && <button className="btn-copy" onClick={() => copy(ai, setToast)}>복사</button>}
            <button className="btn btn-sm btn-primary" disabled={busy} onClick={askAI}>{busy && <span className="spinner" />}{busy ? '분석 중...' : ai ? '다시 분석' : '이번 달 분석 요청'}</button>
          </div>
        </div>
        {ai ? <div className="ai-box">{ai}</div> : <p className="note">카테고리별 합계와 전월 대비 변화를 바탕으로 원장용 코멘트를 작성합니다. 거래 개별 내용은 전송하지 않습니다.</p>}
      </div>
    </>
  );
}

/* ───────────── 수강료 수납 ───────────── */
function Tuition({ state, setState, month, setToast }) {
  const [form, setForm] = useState({ name: '', parentName: '', className: '', fee: '', dueDay: '', phone: '' });
  const [tone, setTone] = useState('polite');
  const [aiMsg, setAiMsg] = useState({});
  const [busyId, setBusyId] = useState('');
  const students = state.students || [];
  const pm = state.payments?.[month] || {};
  const active = students.filter((s) => s.active !== false);
  const paidList = active.filter((s) => pm[s.id]?.paid);
  const unpaid = active.filter((s) => !pm[s.id]?.paid);
  const expected = active.reduce((a, s) => a + Number(s.fee || 0), 0);
  const collected = paidList.reduce((a, s) => a + Number(pm[s.id]?.amount ?? s.fee ?? 0), 0);

  const setPayment = (sid, data) => setState((s) => {
    const next = { ...(s.payments || {}) };
    const m = { ...(next[month] || {}) };
    if (data) m[sid] = data; else delete m[sid];
    next[month] = m;
    return { ...s, payments: next };
  });

  const addStudent = () => {
    if (!form.name.trim() || !Number(form.fee)) { setToast('이름과 수강료를 입력하세요.'); return; }
    setState((s) => ({ ...s, students: [...(s.students || []), { id: uid(), ...form, fee: Number(form.fee), dueDay: Number(form.dueDay) || 25, active: true }] }));
    setForm({ name: '', parentName: '', className: '', fee: '', dueDay: '', phone: '' });
  };
  const updStudent = (id, patch) => setState((s) => ({ ...s, students: s.students.map((x) => (x.id === id ? { ...x, ...patch } : x)) }));
  const delStudent = (id) => { if (window.confirm('학생을 삭제할까요?')) setState((s) => ({ ...s, students: s.students.filter((x) => x.id !== id) })); };

  // 입금 내역과 자동 대조
  const autoMatch = () => {
    const usedKeys = new Set();
    Object.values(state.payments || {}).forEach((m) => Object.values(m).forEach((p) => p.txKey && usedKeys.add(p.txKey)));
    const prevM = shiftMonth(month, -1);
    const deposits = (state.txs || []).filter((t) => t.amount > 0 && !usedKeys.has(t.key)
      && (t.month === month || (t.month === prevM && Number(t.date.slice(8)) >= 24))); // 전월 24일 이후 선납 포함
    let matched = 0;
    const updates = {};
    for (const s of unpaid) {
      const names = [s.name, s.parentName].filter((n) => n && n.trim().length >= 2).map((n) => n.replace(/\s/g, ''));
      if (!names.length) continue;
      const fee = Number(s.fee || 0);
      const cands = deposits.filter((t) => !usedKeys.has(t.key) && names.some((n) => t.desc.replace(/\s/g, '').includes(n)));
      if (!cands.length) continue;
      // 같은 달 + 금액 일치 우선
      cands.sort((a, b) => {
        const sa = (a.month === month ? 0 : 2) + (a.amount === fee ? 0 : Math.abs(a.amount - fee) / Math.max(fee, 1) <= 0.1 ? 1 : 3);
        const sb = (b.month === month ? 0 : 2) + (b.amount === fee ? 0 : Math.abs(b.amount - fee) / Math.max(fee, 1) <= 0.1 ? 1 : 3);
        return sa - sb;
      });
      const best = cands[0];
      if (fee && Math.abs(best.amount - fee) / fee > 0.5) continue; // 금액 차이가 너무 크면 제외
      usedKeys.add(best.key);
      updates[s.id] = { paid: true, date: best.date, amount: best.amount, how: 'auto', txKey: best.key, desc: best.desc };
      matched++;
    }
    if (matched) setState((s) => ({ ...s, payments: { ...(s.payments || {}), [month]: { ...(s.payments?.[month] || {}), ...updates } } }));
    setToast(matched ? `${matched}명 입금 확인 완료` : '대조되는 입금이 없습니다. 거래내역을 먼저 가져왔는지, 입금자명이 학생/보호자 이름과 같은지 확인하세요.');
  };

  const template = (s) => {
    const who = s.parentName ? `${s.parentName}님` : `${s.name} 학생 보호자님`;
    const base = `[${state.profile.name}] ${who}, 안녕하세요. ${monthLabel(month)} ${s.name} 학생 수강료 ${won(s.fee)}이(가) 아직 확인되지 않아 안내드립니다.`;
    return tone === 'firm'
      ? `${base} 납부 기한(매월 ${s.dueDay}일)이 지났으니 금일 중 입금 부탁드립니다. 이미 입금하셨다면 알려주세요. 감사합니다.`
      : `${base} 확인 후 입금 부탁드리며, 이미 입금하셨다면 회신 주시면 바로 확인하겠습니다. 감사합니다.`;
  };
  const polish = async (s) => {
    setBusyId(s.id);
    try {
      const r = await aiCall('message', { academy: state.profile.name, student: s.name, className: s.className, amount: s.fee, month: monthLabel(month), dueDay: s.dueDay, tone, draft: template(s) });
      setAiMsg((m) => ({ ...m, [s.id]: r.text }));
    } catch (e) { setToast('AI 문구 생성 실패: ' + e.message); }
    setBusyId('');
  };

  return (
    <>
      <div className="grid g4" style={{ marginBottom: 20 }}>
        <StatTile label="등록 학생" raw={`${active.length}명`} />
        <StatTile label="수납 완료" raw={`${paidList.length}명 · ${pct(paidList.length, active.length)}%`} />
        <StatTile label="수납 금액" value={collected} tone="pos" />
        <StatTile label="미수납 예정액" value={unpaid.reduce((a, s) => a + Number(s.fee || 0), 0)} tone={unpaid.length ? 'neg' : undefined} />
      </div>

      <div className="card">
        <div className="card-title">
          <span>{monthLabel(month)} 수납 현황 <small>예정 {won(expected)}</small></span>
          <div className="btn-row">
            <button className="btn btn-sm btn-primary" onClick={autoMatch} disabled={!unpaid.length}>입금 내역 자동 대조</button>
          </div>
        </div>
        {!students.length ? <Empty>아래에서 학생을 등록하세요. 등록 후 <b>입금 내역 자동 대조</b>를 누르면 거래내역의 입금자명과 비교해 납부를 자동 체크합니다.</Empty> : (
          <div style={{ overflowX: 'auto' }}>
            <table className="tbl">
              <thead><tr><th>학생</th><th>보호자</th><th>반</th><th className="num">수강료</th><th>기한</th><th>상태</th><th>입금 정보</th><th></th></tr></thead>
              <tbody>
                {students.map((s) => {
                  const p = pm[s.id];
                  const overdue = !p?.paid && s.active !== false && month <= thisMonth() && (month < thisMonth() || new Date().getDate() > Number(s.dueDay || 25));
                  return (
                    <tr key={s.id} style={{ opacity: s.active === false ? 0.5 : 1 }}>
                      <td><input type="text" value={s.name} onChange={(e) => updStudent(s.id, { name: e.target.value })} style={{ width: 90 }} /></td>
                      <td><input type="text" value={s.parentName || ''} placeholder="입금자명" onChange={(e) => updStudent(s.id, { parentName: e.target.value })} style={{ width: 90 }} /></td>
                      <td><input type="text" value={s.className || ''} onChange={(e) => updStudent(s.id, { className: e.target.value })} style={{ width: 80 }} /></td>
                      <td className="num"><input type="number" value={s.fee} onChange={(e) => updStudent(s.id, { fee: Number(e.target.value) })} style={{ width: 100, textAlign: 'right' }} /></td>
                      <td><input type="number" value={s.dueDay} min={1} max={31} onChange={(e) => updStudent(s.id, { dueDay: Number(e.target.value) })} style={{ width: 50 }} />일</td>
                      <td>
                        {s.active === false ? <span className="chip gray">휴원</span>
                          : p?.paid ? <span className="chip green">납부</span>
                          : overdue ? <span className="chip red">미납</span> : <span className="chip amber">대기</span>}
                      </td>
                      <td className="note">{p?.paid ? `${p.date} ${won(p.amount)} ${p.how === 'auto' ? '(자동)' : '(수동)'}` : '-'}</td>
                      <td>
                        <div className="row-actions">
                          {p?.paid
                            ? <button className="btn btn-sm btn-ghost" onClick={() => setPayment(s.id, null)}>취소</button>
                            : <button className="btn btn-sm btn-ghost" onClick={() => setPayment(s.id, { paid: true, date: todayISO(), amount: s.fee, how: 'manual' })}>납부 체크</button>}
                          <button className="btn btn-sm btn-ghost" title={s.active === false ? '복귀' : '휴원 처리'} onClick={() => updStudent(s.id, { active: s.active === false })}>{s.active === false ? '복귀' : '휴원'}</button>
                          <button className="btn btn-sm btn-ghost" onClick={() => delStudent(s.id)}>✕</button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <div className="grid g4" style={{ marginTop: 16, alignItems: 'end' }}>
          <div className="field"><label className="fl">학생 이름 *</label><input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
          <div className="field"><label className="fl">보호자(입금자명)</label><input type="text" value={form.parentName} onChange={(e) => setForm({ ...form, parentName: e.target.value })} /></div>
          <div className="field"><label className="fl">반</label><input type="text" value={form.className} onChange={(e) => setForm({ ...form, className: e.target.value })} placeholder="고2 내신A" /></div>
          <div className="field"><label className="fl">월 수강료 *</label><input type="number" value={form.fee} onChange={(e) => setForm({ ...form, fee: e.target.value })} placeholder="350000" /></div>
          <div className="field"><label className="fl">납부 기한(일)</label><input type="number" value={form.dueDay} onChange={(e) => setForm({ ...form, dueDay: e.target.value })} placeholder="25" /></div>
          <div className="field"><label className="fl">연락처(선택)</label><input type="text" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></div>
          <button className="btn btn-primary" onClick={addStudent}>+ 학생 추가</button>
        </div>
      </div>

      {unpaid.length > 0 && (
        <div className="card">
          <div className="card-title">
            <span>미납 안내 문자 <small>{unpaid.length}명</small></span>
            <div className="btn-row">
              <select value={tone} onChange={(e) => setTone(e.target.value)}>
                <option value="polite">1차 안내 (부드럽게)</option>
                <option value="firm">2차 안내 (분명하게)</option>
              </select>
              <button className="btn-copy" onClick={() => copy(unpaid.map((s) => `${s.name}${s.phone ? ` (${s.phone})` : ''}\n${aiMsg[s.id] || template(s)}`).join('\n\n'), setToast)}>전체 복사</button>
            </div>
          </div>
          {unpaid.map((s) => (
            <div key={s.id} style={{ borderBottom: '1px solid var(--graylt)', padding: '10px 0' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 4 }}>
                <b>{s.name}</b> <span className="note">{s.className} · {won(s.fee)}{s.phone ? ` · ${s.phone}` : ''}</span>
                <div className="btn-row">
                  <button className="btn btn-sm btn-ghost" disabled={busyId === s.id} onClick={() => polish(s)}>{busyId === s.id ? '작성 중...' : 'AI로 다듬기'}</button>
                  <button className="btn-copy" onClick={() => copy(aiMsg[s.id] || template(s), setToast)}>복사</button>
                </div>
              </div>
              <div style={{ fontSize: 13.5, background: 'var(--paper)', padding: '8px 12px', whiteSpace: 'pre-wrap' }}>{aiMsg[s.id] || template(s)}</div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

/* ───────────── 강사 급여 ───────────── */
function Payroll({ state, setState, month, setToast }) {
  const [form, setForm] = useState({ name: '', type: 'freelancer', payMode: 'hourly', rate: '' });
  const [showRates, setShowRates] = useState(false);
  const list = state.instructors || [];
  const rates = { ...DEFAULT_RATES, ...(state.rates || {}) };
  const upd = (id, patch) => setState((s) => ({ ...s, instructors: s.instructors.map((x) => (x.id === id ? { ...x, ...patch } : x)) }));
  const updMonthly = (inst, field, v) => upd(inst.id, { [field]: { ...(inst[field] || {}), [month]: Number(v) || 0 } });
  const add = () => {
    if (!form.name.trim() || !Number(form.rate)) { setToast('이름과 급여 기준을 입력하세요.'); return; }
    setState((s) => ({ ...s, instructors: [...(s.instructors || []), { id: uid(), ...form, rate: Number(form.rate), hours: {}, extra: {}, incomeTax: {} }] }));
    setForm({ name: '', type: 'freelancer', payMode: 'hourly', rate: '' });
  };
  const rows = list.map((i) => ({ inst: i, pay: calcPay(i, month, rates) }));
  const totals = rows.reduce((a, r) => ({ base: a.base + r.pay.base, net: a.net + r.pay.net, withheld: a.withheld + r.pay.withheld, ded: a.ded + r.pay.totalDeduction }), { base: 0, net: 0, withheld: 0, ded: 0 });
  const freelancerWithheld = rows.filter((r) => r.inst.type === 'freelancer').reduce((a, r) => a + r.pay.withheld, 0);

  const slipText = () => rows.map(({ inst, pay }) =>
    `[${monthLabel(month)} 급여명세] ${inst.name} (${inst.type === 'freelancer' ? '사업소득 3.3%' : '4대보험'})\n` +
    `지급액 ${won(pay.base)}${inst.payMode === 'hourly' ? ` (${pay.hours}시간 × ${won(inst.rate)})` : ''}${pay.extra ? ` + 추가 ${won(pay.extra)}` : ''}\n` +
    pay.deductions.map(([k, v]) => `  - ${k} ${won(v)}`).join('\n') + `\n공제 합계 ${won(pay.totalDeduction)} → 실지급 ${won(pay.net)}`
  ).join('\n\n');

  return (
    <>
      <div className="grid g4" style={{ marginBottom: 20 }}>
        <StatTile label="총 지급액(세전)" value={totals.base} />
        <StatTile label="실지급 합계" value={totals.net} tone="pos" />
        <StatTile label="원천징수 합계" value={totals.withheld} />
        <StatTile label={`${monthLabel(shiftMonth(month, 1))} 10일 원천세 납부 예정`} value={totals.withheld} tone="neg" />
      </div>
      <div className="card">
        <div className="card-title">
          <span>{monthLabel(month)} 강사 급여</span>
          <div className="btn-row">
            <button className="btn btn-sm btn-ghost" onClick={() => setShowRates((v) => !v)}>4대보험 요율</button>
            {rows.length > 0 && <button className="btn-copy" onClick={() => copy(slipText(), setToast)}>급여명세 복사</button>}
          </div>
        </div>
        {showRates && (
          <div className="banner" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 10 }}>
            {[['pension', '국민연금 %'], ['health', '건강보험 %'], ['care', '장기요양(건보 대비 %)'], ['employment', '고용보험 %'], ['pensionCap', '국민연금 상한(원)']].map(([k, l]) => (
              <div className="field" key={k}><label className="fl">{l}</label><input type="number" step="0.001" value={rates[k]} onChange={(e) => setState((s) => ({ ...s, rates: { ...rates, [k]: Number(e.target.value) } }))} /></div>
            ))}
            <div className="note" style={{ gridColumn: '1/-1' }}>근로자 부담분 기준의 간이 추정입니다. 소득세는 간이세액표에 따라 다르므로 직접 입력하세요. 요율은 매년 바뀌니 확인 후 수정하세요.</div>
          </div>
        )}
        {!list.length ? <Empty>아래에서 강사를 등록하세요. 시급제는 월별 시수를 입력하면 자동 계산됩니다.</Empty> : (
          <div style={{ overflowX: 'auto' }}>
            <table className="tbl">
              <thead><tr><th>강사</th><th>형태</th><th>기준</th><th className="num">단가/월급</th><th className="num">시수</th><th className="num">추가 수당</th><th className="num">소득세(근로자)</th><th className="num">지급액</th><th className="num">공제</th><th className="num">실지급</th><th></th></tr></thead>
              <tbody>
                {rows.map(({ inst, pay }) => (
                  <tr key={inst.id}>
                    <td><input type="text" value={inst.name} onChange={(e) => upd(inst.id, { name: e.target.value })} style={{ width: 80 }} /></td>
                    <td>
                      <select value={inst.type} onChange={(e) => upd(inst.id, { type: e.target.value })}>
                        <option value="freelancer">3.3%</option><option value="employee">4대보험</option>
                      </select>
                    </td>
                    <td>
                      <select value={inst.payMode} onChange={(e) => upd(inst.id, { payMode: e.target.value })}>
                        <option value="hourly">시급</option><option value="monthly">월급</option>
                      </select>
                    </td>
                    <td className="num"><input type="number" value={inst.rate} onChange={(e) => upd(inst.id, { rate: Number(e.target.value) })} style={{ width: 100, textAlign: 'right' }} /></td>
                    <td className="num">{inst.payMode === 'hourly' ? <input type="number" step="0.5" value={inst.hours?.[month] ?? ''} placeholder="0" onChange={(e) => updMonthly(inst, 'hours', e.target.value)} style={{ width: 64, textAlign: 'right' }} /> : '-'}</td>
                    <td className="num"><input type="number" value={inst.extra?.[month] ?? ''} placeholder="0" onChange={(e) => updMonthly(inst, 'extra', e.target.value)} style={{ width: 90, textAlign: 'right' }} /></td>
                    <td className="num">{inst.type === 'employee' ? <input type="number" value={inst.incomeTax?.[month] ?? ''} placeholder="0" onChange={(e) => updMonthly(inst, 'incomeTax', e.target.value)} style={{ width: 90, textAlign: 'right' }} /> : <span className="muted">자동</span>}</td>
                    <td className="num">{won(pay.base)}</td>
                    <td className="num neg" title={pay.deductions.map(([k, v]) => `${k} ${won(v)}`).join('\n')}>-{won(pay.totalDeduction)}</td>
                    <td className="num" style={{ fontWeight: 700 }}>{won(pay.net)}</td>
                    <td><button className="btn btn-sm btn-ghost" onClick={() => { if (window.confirm('강사를 삭제할까요?')) setState((s) => ({ ...s, instructors: s.instructors.filter((x) => x.id !== inst.id) })); }}>✕</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="sticky-sum">
              <span>합계 지급 {won(totals.base)} · 공제 {won(totals.ded)} · 실지급 {won(totals.net)}</span>
              <span>3.3% 원천세 {won(freelancerWithheld)} → {monthLabel(shiftMonth(month, 1))} 10일 신고·납부, 간이지급명세서는 말일까지</span>
            </div>
          </div>
        )}
        <div className="grid g4" style={{ marginTop: 16, alignItems: 'end' }}>
          <div className="field"><label className="fl">강사 이름 *</label><input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
          <div className="field"><label className="fl">고용 형태</label>
            <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}><option value="freelancer">프리랜서 (3.3%)</option><option value="employee">근로자 (4대보험)</option></select></div>
          <div className="field"><label className="fl">급여 기준</label>
            <select value={form.payMode} onChange={(e) => setForm({ ...form, payMode: e.target.value })}><option value="hourly">시급</option><option value="monthly">월급</option></select></div>
          <div className="field"><label className="fl">{form.payMode === 'hourly' ? '시급(원) *' : '월급(원) *'}</label><input type="number" value={form.rate} onChange={(e) => setForm({ ...form, rate: e.target.value })} placeholder={form.payMode === 'hourly' ? '40000' : '2500000'} /></div>
          <button className="btn btn-primary" onClick={add}>+ 강사 추가</button>
        </div>
      </div>
    </>
  );
}

/* ───────────── 세무 일정 ───────────── */
function TaxCalendar({ state, setState }) {
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const p = state.profile;
  const setP = (patch) => setState((s) => ({ ...s, profile: { ...s.profile, ...patch } }));
  const events = useMemo(() => buildTaxCalendar(year, p), [year, p]);
  const today = todayISO();
  const upcoming = useMemo(() => {
    const all = [...buildTaxCalendar(thisYear, p), ...buildTaxCalendar(thisYear + 1, p)];
    return all.filter((e) => e.date >= today && daysBetween(today, e.date) <= 45).slice(0, 8);
  }, [p, today, thisYear]);
  const byMonth = {};
  events.forEach((e) => { (byMonth[e.date.slice(0, 7)] ||= []).push(e); });

  return (
    <>
      <div className="card">
        <div className="card-title"><span>학원 설정</span><small>일정에 반영됩니다</small></div>
        <div className="btn-row" style={{ gap: 18 }}>
          <label style={{ fontSize: 13 }}><input type="checkbox" checked={!!p.hasEmployees} onChange={(e) => setP({ hasEmployees: e.target.checked })} /> 4대보험 근로자 있음</label>
          <label style={{ fontSize: 13 }}><input type="checkbox" checked={!!p.halfYearWithholding} onChange={(e) => setP({ halfYearWithholding: e.target.checked })} /> 원천세 반기납부 승인 사업자</label>
          <label style={{ fontSize: 13 }}><input type="checkbox" checked={!!p.hasTaxableSales} onChange={(e) => setP({ hasTaxableSales: e.target.checked })} /> 교재 판매 등 과세 매출 있음(부가세 겸영)</label>
          <label style={{ fontSize: 13 }}><input type="checkbox" checked={!!p.sincere} onChange={(e) => setP({ sincere: e.target.checked })} /> 성실신고확인 대상</label>
        </div>
        <p className="note" style={{ marginTop: 8 }}>학원(교육용역)은 부가가치세 면세사업자라 부가세 신고 대신 매년 2월 10일 <b>사업장현황신고</b>를 합니다. 아래 일정은 일반 기준이며, 토·일요일이면 다음 영업일로 표시했습니다(공휴일 미반영). 실제 의무는 세무사와 확인하세요.</p>
      </div>

      <div className="card">
        <div className="card-title"><span>다가오는 일정 <small>45일 이내</small></span></div>
        {!upcoming.length ? <Empty>45일 이내 일정이 없습니다.</Empty> : upcoming.map((e, i) => {
          const d = daysBetween(today, e.date);
          return (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: '90px 1fr', gap: 12, padding: '10px 0', borderBottom: '1px solid var(--graylt)' }}>
              <div>
                <div style={{ fontWeight: 800, color: d <= 7 ? 'var(--red)' : 'var(--navy)' }}>{d === 0 ? '오늘' : `D-${d}`}</div>
                <div className="note">{e.date.slice(5).replace('-', '/')}</div>
              </div>
              <div>
                <div style={{ fontWeight: 700 }}>{e.title} <span className="chip gray">{KIND_LABEL[e.kind]}</span></div>
                <div className="note">{e.desc}</div>
                <div className="note" style={{ marginTop: 3 }}>준비: {e.docs.join(' · ')}</div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="card">
        <div className="card-title">
          <span>연간 일정</span>
          <select value={year} onChange={(e) => setYear(Number(e.target.value))}>
            {[thisYear - 1, thisYear, thisYear + 1].map((y) => <option key={y} value={y}>{y}년</option>)}
          </select>
        </div>
        {Object.entries(byMonth).map(([ym, list]) => (
          <div key={ym} style={{ marginBottom: 12 }}>
            <div style={{ fontWeight: 800, color: 'var(--navy)', fontSize: 13.5, marginBottom: 4 }}>{monthLabel(ym)}</div>
            {list.map((e, i) => (
              <div key={i} style={{ display: 'grid', gridTemplateColumns: '54px 1fr', gap: 10, fontSize: 13, padding: '4px 0', opacity: e.date < today ? 0.55 : 1 }}>
                <span style={{ fontWeight: 700 }}>{Number(e.date.slice(8))}일</span>
                <span>{e.title} <span className="muted">— {e.desc}</span></span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </>
  );
}

import { useAcademy, today, thisMonth, thisYear, weekdayOf, fmtMoney, loadSample, contractState, daysBetween, leaveBalance } from '../../lib/academyStore';
import { computePay } from './Payroll';
import { Btn, Badge, PageHead, Stat, Empty, useManage, statusTone } from './ui';

export default function Dashboard() {
  const { employees, attendance, leaves, payrolls, contracts, settings } = useAcademy();
  const { go, notify } = useManage();
  const t = today(), m = thisMonth(), y = thisYear(), wd = weekdayOf(t);
  const staff = employees.filter((e) => e.status === '재직');
  const todayAtt = attendance.filter((a) => a.date === t);
  const checked = staff.filter((e) => todayAtt.some((a) => a.employeeId === e.id));
  const abnormal = todayAtt.filter((a) => ['지각', '조퇴', '결근'].includes(a.status));
  const onLeaveToday = leaves.filter((l) => l.status === '승인' && l.start <= t && (l.end || l.start) >= t);
  const pendingLeaves = leaves.filter((l) => l.status === '대기');
  const expiring = contracts.map((c) => ({ ...c, state: contractState(c, t) })).filter((c) => c.state === '만료임박').sort((a, b) => a.end.localeCompare(b.end));
  const monthPay = payrolls.filter((p) => p.month === m).map((p) => ({ ...p, calc: computePay(p, employees.find((e) => e.id === p.employeeId), settings.rates) }));
  const payNet = monthPay.reduce((s, p) => s + p.calc.net, 0);
  const unpaid = monthPay.filter((p) => p.status !== '지급완료');
  const upcomingLeaves = leaves.filter((l) => l.status === '승인' && l.start > t && daysBetween(t, l.start) <= 14).sort((a, b) => a.start.localeCompare(b.start));
  const anniv = staff.filter((e) => e.hireDate && e.hireDate.slice(5) >= t.slice(5) && e.hireDate.slice(5) <= (daysBetween(t, t) === 0 ? t.slice(5, 8) + '31' : '')).slice(0, 5);
  const isEmpty = !employees.length;
  const name = (id) => employees.find((e) => e.id === id)?.name || '-';

  return (
    <>
      <PageHead title="대시보드" desc={`${t} (${wd}) · ${settings.academyName}`} />
      {isEmpty && (
        <div className="mg-card">
          <Empty icon="🏢" title="학원 인사 관리 시스템에 오신 것을 환영합니다" desc="직원을 등록하면 근태·휴가·급여·계약을 한 흐름으로 관리할 수 있습니다. 먼저 둘러보고 싶다면 샘플 데이터를 불러오세요."
            action={<div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap' }}><Btn onClick={() => go('employees')}>직원 등록 시작</Btn><Btn variant="ghost" onClick={() => { loadSample(); notify('샘플 데이터를 불러왔습니다.'); }}>샘플 데이터 불러오기</Btn></div>} />
        </div>
      )}
      <div className="mg-stats">
        <Stat label="재직 인원" value={`${staff.length}명`} sub={`휴직 ${employees.filter((e) => e.status === '휴직').length} · 퇴직 ${employees.filter((e) => e.status === '퇴직').length}`} />
        <Stat label="오늘 출근" value={`${checked.length} / ${staff.length}`} sub={`지각·조퇴·결근 ${abnormal.length} · 휴가 ${onLeaveToday.length}`} tone={abnormal.length ? 'red' : 'green'} />
        <Stat label="휴가 승인 대기" value={`${pendingLeaves.length}건`} tone={pendingLeaves.length ? 'gold' : ''} />
        <Stat label="30일 내 계약 만료" value={`${expiring.length}건`} tone={expiring.length ? 'red' : ''} />
        <Stat label={`${m} 급여 (실지급)`} value={fmtMoney(payNet)} sub={monthPay.length ? `미지급 ${unpaid.length}명 / ${monthPay.length}명` : '급여 미생성'} tone="gold" />
      </div>
      <div className="mg-two">
        <div className="mg-card">
          <div className="mg-card-title">오늘 근태 <Btn size="sm" variant="ghost" onClick={() => go('work')}>근태 관리 →</Btn></div>
          {staff.length ? (
            <ul className="mg-list">{staff.map((e) => { const a = todayAtt.find((x) => x.employeeId === e.id); const lv = onLeaveToday.find((l) => l.employeeId === e.id); return (
              <li key={e.id}><span><b>{e.name}</b> <span className="mg-muted">{e.position}</span></span><span>{a ? <><span className="mg-muted" style={{ marginRight: 6 }}>{a.checkIn}{a.checkOut ? `~${a.checkOut}` : ''}</span><Badge tone={statusTone(a.status)}>{a.status}</Badge></> : lv ? <Badge tone="gold">{lv.type}</Badge> : <Badge tone="gray">미체크</Badge>}</span></li>
            ); })}</ul>
          ) : <div className="mg-muted">재직 중인 직원이 없습니다.</div>}
        </div>
        <div className="mg-card">
          <div className="mg-card-title">휴가 승인 대기 · 예정 <Btn size="sm" variant="ghost" onClick={() => go('leaves')}>휴가 관리 →</Btn></div>
          {pendingLeaves.length || upcomingLeaves.length ? (
            <ul className="mg-list">
              {pendingLeaves.map((l) => <li key={l.id}><span><Badge tone="amber">대기</Badge> <b>{name(l.employeeId)}</b> <Badge tone="gold">{l.type}</Badge> {l.start}{l.end !== l.start ? `~${l.end}` : ''} ({l.days}일)</span></li>)}
              {upcomingLeaves.map((l) => <li key={l.id}><span><Badge tone="green">승인</Badge> <b>{name(l.employeeId)}</b> <Badge tone="gold">{l.type}</Badge> {l.start}{l.end !== l.start ? `~${l.end}` : ''} <span className="mg-muted">D-{daysBetween(t, l.start)}</span></span></li>)}
            </ul>
          ) : <div className="mg-muted">대기 중이거나 2주 내 예정된 휴가가 없습니다.</div>}
        </div>
        <div className="mg-card">
          <div className="mg-card-title">계약 만료 임박 <Btn size="sm" variant="ghost" onClick={() => go('contracts')}>계약 관리 →</Btn></div>
          {expiring.length ? (
            <ul className="mg-list">{expiring.map((c) => <li key={c.id}><span><b>{name(c.employeeId)}</b> <span className="mg-muted">{c.type}</span></span><span><span className="mg-muted" style={{ marginRight: 6 }}>{c.end}</span><Badge tone="red">D-{daysBetween(t, c.end)}</Badge></span></li>)}</ul>
          ) : <div className="mg-muted">30일 내 만료되는 계약이 없습니다.</div>}
        </div>
        <div className="mg-card">
          <div className="mg-card-title">{m} 급여 현황 <Btn size="sm" variant="ghost" onClick={() => go('payroll')}>급여 관리 →</Btn></div>
          {monthPay.length ? (
            <ul className="mg-list">{monthPay.sort((a, b) => (a.status === '미지급' ? -1 : 0) - (b.status === '미지급' ? -1 : 0)).slice(0, 8).map((p) => <li key={p.id}><span><b>{name(p.employeeId)}</b> <Badge tone={statusTone(p.status)}>{p.status}</Badge></span><span>{fmtMoney(p.calc.net)}</span></li>)}{monthPay.length > 8 && <li className="mg-muted">외 {monthPay.length - 8}명</li>}</ul>
          ) : <div className="mg-muted">아직 이번 달 급여를 생성하지 않았습니다.</div>}
        </div>
      </div>
      {staff.length > 0 && (
        <div className="mg-card">
          <div className="mg-card-title">{y}년 연차 잔여 (재직자)</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {staff.map((e) => { const b = leaveBalance(e, leaves, y, settings); return <Badge key={e.id} tone={b.left < 0 ? 'red' : b.left <= 2 ? 'amber' : 'navy'}>{e.name} {b.left}/{b.total}일</Badge>; })}
          </div>
        </div>
      )}
    </>
  );
}

import { useAcademy, today, thisMonth, weekdayOf, fmtMoney, paymentStatus, loadSample } from '../../lib/academyStore';
import { Btn, Badge, PageHead, Stat, Empty, useManage, statusTone } from './ui';

export default function Dashboard() {
  const { students, classes, teachers, attendance, payments, counseling } = useAcademy();
  const { go, notify } = useManage();
  const t = today(), m = thisMonth(), wd = weekdayOf(t);
  const active = students.filter((s) => s.status === '재원');
  const todayClasses = classes.filter((c) => (c.days || []).includes(wd)).sort((a, b) => (a.time || '').localeCompare(b.time || ''));
  const monthPays = payments.filter((p) => p.month === m);
  const unpaid = monthPays.filter((p) => paymentStatus(p) !== '완납');
  const unpaidAmount = unpaid.reduce((s, p) => s + Math.max((Number(p.amount) || 0) - (Number(p.paidAmount) || 0), 0), 0);
  const inWeek = (d) => { if (!d) return false; const diff = (new Date(d) - new Date(t)) / 86400000; return diff >= -30 && diff <= 7; };
  const followUps = counseling.filter((c) => inWeek(c.followUp)).sort((a, b) => a.followUp.localeCompare(b.followUp));
  const recent = [...students].sort((a, b) => (b.joinDate || '').localeCompare(a.joinDate || '')).slice(0, 5);
  const absentToday = attendance.filter((a) => a.date === t && a.status === '결석');
  const isEmpty = !students.length && !classes.length && !teachers.length;

  return (
    <>
      <PageHead title="대시보드" desc={`${t} (${wd})`} />
      {isEmpty && (
        <div className="mg-card">
          <Empty icon="🏫" title="학원 관리 시스템에 오신 것을 환영합니다" desc="강사 → 반 → 학생 순서로 등록하면 출결과 수납이 자동으로 연결됩니다. 먼저 둘러보고 싶다면 샘플 데이터를 불러오세요."
            action={<div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap' }}><Btn onClick={() => go('students')}>학생 등록 시작</Btn><Btn variant="ghost" onClick={() => { loadSample(); notify('샘플 데이터를 불러왔습니다.'); }}>샘플 데이터 불러오기</Btn></div>} />
        </div>
      )}
      <div className="mg-stats">
        <Stat label="재원생" value={`${active.length}명`} sub={`휴원 ${students.filter((s) => s.status === '휴원').length} · 퇴원 ${students.filter((s) => s.status === '퇴원').length}`} />
        <Stat label="운영 반" value={`${classes.length}개`} sub={`오늘 수업 ${todayClasses.length}개`} />
        <Stat label="재직 강사" value={`${teachers.filter((x) => x.status === '재직').length}명`} tone="gold" />
        <Stat label={`${m} 미수금`} value={fmtMoney(unpaidAmount)} sub={monthPays.length ? `미납·부분납 ${unpaid.length}명 / 청구 ${monthPays.length}건` : '청구 미생성'} tone="red" />
      </div>
      <div className="mg-two">
        <div className="mg-card">
          <div className="mg-card-title">오늘 수업 <Btn size="sm" variant="ghost" onClick={() => go('attendance')}>출석 체크 →</Btn></div>
          {todayClasses.length ? (
            <ul className="mg-list">{todayClasses.map((c) => {
              const roster = active.filter((s) => (s.classIds || []).includes(c.id));
              const checked = roster.filter((s) => attendance.some((a) => a.date === t && a.classId === c.id && a.studentId === s.id)).length;
              return <li key={c.id}><span><b>{c.name}</b> <span className="mg-muted">{c.time} · {teachers.find((x) => x.id === c.teacherId)?.name || '강사 미지정'}</span></span><span><Badge tone={checked === roster.length && roster.length ? 'green' : checked ? 'amber' : 'gray'}>출결 {checked}/{roster.length}</Badge></span></li>;
            })}</ul>
          ) : <div className="mg-muted">오늘은 예정된 수업이 없습니다.</div>}
          {absentToday.length > 0 && <div className="mg-note-box" style={{ marginTop: 12 }}>오늘 결석 {absentToday.length}명: {absentToday.map((a) => students.find((s) => s.id === a.studentId)?.name).filter(Boolean).join(', ')}</div>}
        </div>
        <div className="mg-card">
          <div className="mg-card-title">미납 현황 ({m}) <Btn size="sm" variant="ghost" onClick={() => go('payments')}>수납 관리 →</Btn></div>
          {unpaid.length ? (
            <ul className="mg-list">{unpaid.slice(0, 8).map((p) => { const s = students.find((x) => x.id === p.studentId); return <li key={p.id}><span><b>{s?.name || '-'}</b> <Badge tone={statusTone(paymentStatus(p))}>{paymentStatus(p)}</Badge></span><span style={{ color: 'var(--red)', fontWeight: 700 }}>{fmtMoney((Number(p.amount) || 0) - (Number(p.paidAmount) || 0))}</span></li>; })}
              {unpaid.length > 8 && <li className="mg-muted">외 {unpaid.length - 8}명</li>}
            </ul>
          ) : <div className="mg-muted">{monthPays.length ? '모든 학생이 납부를 완료했습니다. 🎉' : '아직 이번 달 청구를 생성하지 않았습니다.'}</div>}
        </div>
        <div className="mg-card">
          <div className="mg-card-title">후속 상담 예정 <Btn size="sm" variant="ghost" onClick={() => go('counseling')}>상담 기록 →</Btn></div>
          {followUps.length ? (
            <ul className="mg-list">{followUps.map((c) => { const s = students.find((x) => x.id === c.studentId); return <li key={c.id}><span><Badge tone={c.followUp < t ? 'red' : c.followUp === t ? 'amber' : 'blue'}>{c.followUp}</Badge> <b>{s?.name}</b> <span className="mg-muted">{c.type}</span></span></li>; })}</ul>
          ) : <div className="mg-muted">일주일 내 예정된 후속 상담이 없습니다.</div>}
        </div>
        <div className="mg-card">
          <div className="mg-card-title">최근 등록 학생 <Btn size="sm" variant="ghost" onClick={() => go('students')}>학생 관리 →</Btn></div>
          {recent.length ? (
            <ul className="mg-list">{recent.map((s) => <li key={s.id}><span><b>{s.name}</b> <span className="mg-muted">{s.school} {s.grade}</span></span><span className="mg-muted">{s.joinDate}</span></li>)}</ul>
          ) : <div className="mg-muted">등록된 학생이 없습니다.</div>}
        </div>
      </div>
    </>
  );
}

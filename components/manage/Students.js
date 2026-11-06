import { useMemo, useState } from 'react';
import { useAcademy, addItem, updateItem, removeStudentCascade, GRADES, STUDENT_STATUS, today, thisMonth, fmtPhone, fmtMoney, studentFee, paymentStatus } from '../../lib/academyStore';
import { Btn, Badge, Field, Modal, Table, ChipSelect, PageHead, Empty, useManage, statusTone } from './ui';

const blank = () => ({ name: '', school: '', grade: '고1', phone: '', parentPhone: '', classIds: [], status: '재원', joinDate: today(), memo: '' });

export function StudentForm({ initial, onClose }) {
  const { classes } = useAcademy();
  const { notify } = useManage();
  const [f, setF] = useState(initial ? { ...blank(), ...initial } : blank());
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const save = () => {
    if (!f.name.trim()) return notify('학생 이름을 입력하세요.');
    const data = { ...f, name: f.name.trim(), phone: f.phone.replace(/\D/g, ''), parentPhone: f.parentPhone.replace(/\D/g, '') };
    if (initial?.id) { updateItem('students', initial.id, data); notify('학생 정보를 수정했습니다.'); }
    else { addItem('students', data); notify('학생을 등록했습니다.'); }
    onClose();
  };

  return (
    <Modal title={initial?.id ? '학생 정보 수정' : '학생 등록'} onClose={onClose}
      footer={<><Btn variant="soft" onClick={onClose}>취소</Btn><Btn onClick={save}>저장</Btn></>}>
      <div className="mg-form">
        <Field label="이름" required><input className="mg-input" value={f.name} onChange={set('name')} placeholder="홍길동" autoFocus /></Field>
        <Field label="상태"><select className="mg-select" value={f.status} onChange={set('status')}>{STUDENT_STATUS.map((s) => <option key={s}>{s}</option>)}</select></Field>
        <Field label="학교"><input className="mg-input" value={f.school} onChange={set('school')} placeholder="OO고등학교" /></Field>
        <Field label="학년"><select className="mg-select" value={f.grade} onChange={set('grade')}>{GRADES.map((g) => <option key={g}>{g}</option>)}</select></Field>
        <Field label="학생 연락처"><input className="mg-input" value={f.phone} onChange={set('phone')} placeholder="010-0000-0000" /></Field>
        <Field label="학부모 연락처"><input className="mg-input" value={f.parentPhone} onChange={set('parentPhone')} placeholder="010-0000-0000" /></Field>
        <Field label="등록일"><input type="date" className="mg-input" value={f.joinDate} onChange={set('joinDate')} /></Field>
        <Field label="수강반" full help={classes.length ? '' : '반 관리에서 반을 먼저 만들면 여기서 선택할 수 있습니다.'}>
          {classes.length ? <ChipSelect options={classes} value={f.classIds} onChange={(v) => setF({ ...f, classIds: v })} labelOf={(c) => `${c.name} (${fmtMoney(c.fee)})`} keyOf={(c) => c.id} /> : <span className="mg-muted">등록된 반이 없습니다.</span>}
        </Field>
        <Field label="메모" full><textarea className="mg-textarea" value={f.memo} onChange={set('memo')} placeholder="특이사항, 목표, 성적 등" /></Field>
      </div>
    </Modal>
  );
}

export function StudentDetail({ id, onClose, onEdit }) {
  const { students, classes, teachers, attendance, payments, counseling } = useAcademy();
  const { notify, go } = useManage();
  const s = students.find((x) => x.id === id);
  if (!s) return null;
  const month = thisMonth();
  const myClasses = (s.classIds || []).map((cid) => classes.find((c) => c.id === cid)).filter(Boolean);
  const att = attendance.filter((a) => a.studentId === id && a.date.startsWith(month));
  const attCount = (st) => att.filter((a) => a.status === st).length;
  const pays = payments.filter((p) => p.studentId === id).sort((a, b) => b.month.localeCompare(a.month)).slice(0, 6);
  const cons = counseling.filter((c) => c.studentId === id).sort((a, b) => b.date.localeCompare(a.date)).slice(0, 5);

  const del = () => {
    if (!window.confirm(`${s.name} 학생을 삭제할까요?\n출결·수납·상담 기록도 함께 삭제됩니다.`)) return;
    removeStudentCascade(id); notify('학생을 삭제했습니다.'); onClose();
  };

  return (
    <Modal title={<>{s.name} <Badge tone={statusTone(s.status)}>{s.status}</Badge></>} onClose={onClose} wide
      footer={<><Btn variant="danger" className="left" onClick={del}>삭제</Btn><Btn variant="soft" onClick={onClose}>닫기</Btn><Btn onClick={() => onEdit(s)}>수정</Btn></>}>
      <div className="mg-detail-grid">
        <div><div className="k">학교 · 학년</div><div className="v">{s.school || '-'} {s.grade}</div></div>
        <div><div className="k">학생 연락처</div><div className="v">{fmtPhone(s.phone) || '-'}</div></div>
        <div><div className="k">학부모 연락처</div><div className="v">{fmtPhone(s.parentPhone) || '-'}</div></div>
        <div><div className="k">등록일</div><div className="v">{s.joinDate || '-'}</div></div>
        <div><div className="k">월 수강료 합계</div><div className="v">{fmtMoney(studentFee(s, classes))}</div></div>
      </div>
      {s.memo && <div className="mg-note-box" style={{ marginTop: 14 }}>{s.memo}</div>}

      <div className="mg-sec">수강반</div>
      {myClasses.length ? (
        <ul className="mg-list">{myClasses.map((c) => {
          const t = teachers.find((x) => x.id === c.teacherId);
          return <li key={c.id}><span><b>{c.name}</b> <span className="mg-muted">{c.days.join('·')} {c.time}{t ? ` · ${t.name}` : ''}</span></span><span>{fmtMoney(c.fee)}</span></li>;
        })}</ul>
      ) : <div className="mg-muted">수강 중인 반이 없습니다.</div>}

      <div className="mg-two">
        <div>
          <div className="mg-sec">이번 달 출결 ({month})</div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {['출석', '지각', '결석', '조퇴'].map((st) => <Badge key={st} tone={statusTone(st)}>{st} {attCount(st)}</Badge>)}
          </div>
        </div>
        <div>
          <div className="mg-sec">최근 수납</div>
          {pays.length ? <ul className="mg-list">{pays.map((p) => <li key={p.id}><span>{p.month} <Badge tone={statusTone(paymentStatus(p))}>{paymentStatus(p)}</Badge></span><span>{fmtMoney(p.paidAmount)} / {fmtMoney(p.amount)}</span></li>)}</ul> : <div className="mg-muted">수납 기록이 없습니다.</div>}
        </div>
      </div>

      <div className="mg-sec">최근 상담 <button className="mg-link-btn" style={{ fontSize: 12, marginLeft: 8 }} onClick={() => { onClose(); go('counseling', { studentId: id }); }}>상담 추가 →</button></div>
      {cons.length ? <ul className="mg-list">{cons.map((c) => <li key={c.id}><span><span className="mg-muted">{c.date}</span> <Badge tone="gold">{c.type}</Badge> {c.content}</span></li>)}</ul> : <div className="mg-muted">상담 기록이 없습니다.</div>}
    </Modal>
  );
}

export default function Students() {
  const { students, classes } = useAcademy();
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('재원');
  const [classId, setClassId] = useState('');
  const [form, setForm] = useState(null);   // null | {} | student
  const [detail, setDetail] = useState(null);

  const rows = useMemo(() => {
    const k = q.trim().toLowerCase();
    return students
      .filter((s) => (status === '전체' ? true : s.status === status))
      .filter((s) => (classId ? (s.classIds || []).includes(classId) : true))
      .filter((s) => !k || [s.name, s.school, s.grade, s.phone, s.parentPhone, s.memo].some((v) => String(v || '').toLowerCase().includes(k)))
      .sort((a, b) => a.name.localeCompare(b.name, 'ko'));
  }, [students, q, status, classId]);

  const columns = [
    { key: 'name', label: '이름', render: (s) => <b>{s.name}</b> },
    { key: 'school', label: '학교 · 학년', render: (s) => <>{s.school || '-'} <span className="mg-muted">{s.grade}</span></> },
    { key: 'classes', label: '수강반', render: (s) => (s.classIds || []).map((cid) => classes.find((c) => c.id === cid)?.name).filter(Boolean).join(', ') || <span className="mg-muted">-</span> },
    { key: 'phone', label: '학생 연락처', render: (s) => fmtPhone(s.phone) || '-' },
    { key: 'parentPhone', label: '학부모 연락처', render: (s) => fmtPhone(s.parentPhone) || '-' },
    { key: 'fee', label: '월 수강료', align: 'r', render: (s) => fmtMoney(studentFee(s, classes)) },
    { key: 'status', label: '상태', align: 'c', render: (s) => <Badge tone={statusTone(s.status)}>{s.status}</Badge> },
    { key: 'joinDate', label: '등록일' },
  ];

  return (
    <>
      <PageHead title="학생 관리" desc={`전체 ${students.length}명 · 재원 ${students.filter((s) => s.status === '재원').length}명`} right={<Btn onClick={() => setForm({})}>+ 학생 등록</Btn>} />
      <div className="mg-card">
        <div className="mg-toolbar">
          <input className="mg-input grow" placeholder="이름·학교·연락처·메모 검색" value={q} onChange={(e) => setQ(e.target.value)} />
          <select className="mg-select" style={{ width: 120 }} value={status} onChange={(e) => setStatus(e.target.value)}>
            {['전체', ...STUDENT_STATUS].map((s) => <option key={s}>{s}</option>)}
          </select>
          <select className="mg-select" style={{ width: 180 }} value={classId} onChange={(e) => setClassId(e.target.value)}>
            <option value="">모든 반</option>
            {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <Table columns={columns} rows={rows} onRowClick={(s) => setDetail(s.id)}
          empty={<Empty icon="🎓" title={students.length ? '조건에 맞는 학생이 없습니다.' : '등록된 학생이 없습니다.'} desc="학생을 등록하면 출결·수납·상담을 함께 관리할 수 있습니다." action={<Btn onClick={() => setForm({})}>+ 학생 등록</Btn>} />} />
        <div className="mg-muted" style={{ marginTop: 8 }}>행을 클릭하면 상세 정보를 볼 수 있습니다.</div>
      </div>
      {form && <StudentForm initial={form.id ? form : null} onClose={() => setForm(null)} />}
      {detail && !form && <StudentDetail id={detail} onClose={() => setDetail(null)} onEdit={(s) => { setForm(s); }} />}
    </>
  );
}

import { useState } from 'react';
import { useAcademy, addItem, updateItem, removeClassCascade, DAYS, fmtMoney } from '../../lib/academyStore';
import { Btn, Badge, Field, Modal, Table, ChipSelect, PageHead, Empty, useManage } from './ui';

const blank = () => ({ name: '', subject: '영어', teacherId: '', days: [], time: '', fee: '', room: '', capacity: '', memo: '' });

function ClassForm({ initial, onClose }) {
  const { teachers } = useAcademy();
  const { notify } = useManage();
  const [f, setF] = useState(initial ? { ...blank(), ...initial } : blank());
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = () => {
    if (!f.name.trim()) return notify('반 이름을 입력하세요.');
    const data = { ...f, name: f.name.trim(), fee: Number(String(f.fee).replace(/\D/g, '')) || 0, capacity: Number(f.capacity) || 0 };
    if (initial?.id) { updateItem('classes', initial.id, data); notify('반 정보를 수정했습니다.'); }
    else { addItem('classes', data); notify('반을 만들었습니다.'); }
    onClose();
  };
  return (
    <Modal title={initial?.id ? '반 정보 수정' : '반 만들기'} onClose={onClose}
      footer={<><Btn variant="soft" onClick={onClose}>취소</Btn><Btn onClick={save}>저장</Btn></>}>
      <div className="mg-form">
        <Field label="반 이름" required><input className="mg-input" value={f.name} onChange={set('name')} placeholder="고1 영어 내신A" autoFocus /></Field>
        <Field label="과목"><input className="mg-input" value={f.subject} onChange={set('subject')} placeholder="영어" /></Field>
        <Field label="담당 강사"><select className="mg-select" value={f.teacherId} onChange={set('teacherId')}><option value="">미지정</option>{teachers.filter((t) => t.status !== '퇴직').map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></Field>
        <Field label="수업 시간"><input className="mg-input" value={f.time} onChange={set('time')} placeholder="16:00~17:30" /></Field>
        <Field label="수업 요일" full><ChipSelect options={DAYS} value={f.days} onChange={(v) => setF({ ...f, days: DAYS.filter((d) => v.includes(d)) })} /></Field>
        <Field label="월 수강료 (원)"><input className="mg-input" inputMode="numeric" value={f.fee} onChange={set('fee')} placeholder="250000" /></Field>
        <Field label="정원"><input className="mg-input" inputMode="numeric" value={f.capacity} onChange={set('capacity')} placeholder="10" /></Field>
        <Field label="강의실"><input className="mg-input" value={f.room} onChange={set('room')} placeholder="1강의실" /></Field>
        <Field label="메모" full><textarea className="mg-textarea" value={f.memo} onChange={set('memo')} placeholder="교재, 진도 계획 등" /></Field>
      </div>
    </Modal>
  );
}

function ClassDetail({ id, onClose, onEdit }) {
  const { classes, students, teachers } = useAcademy();
  const { notify } = useManage();
  const [addId, setAddId] = useState('');
  const c = classes.find((x) => x.id === id);
  if (!c) return null;
  const t = teachers.find((x) => x.id === c.teacherId);
  const members = students.filter((s) => (s.classIds || []).includes(id)).sort((a, b) => a.name.localeCompare(b.name, 'ko'));
  const candidates = students.filter((s) => s.status !== '퇴원' && !(s.classIds || []).includes(id));
  const addStudent = () => {
    if (!addId) return;
    const s = students.find((x) => x.id === addId);
    updateItem('students', addId, { classIds: [...(s.classIds || []), id] });
    setAddId(''); notify(`${s.name} 학생을 추가했습니다.`);
  };
  const removeStudent = (s) => {
    if (!window.confirm(`${s.name} 학생을 이 반에서 제외할까요?`)) return;
    updateItem('students', s.id, { classIds: (s.classIds || []).filter((x) => x !== id) });
  };
  const del = () => {
    if (!window.confirm(`"${c.name}" 반을 삭제할까요?\n학생의 수강반 목록과 이 반의 출결 기록에서도 제거됩니다.`)) return;
    removeClassCascade(id); notify('반을 삭제했습니다.'); onClose();
  };
  return (
    <Modal title={c.name} onClose={onClose} wide
      footer={<><Btn variant="danger" className="left" onClick={del}>삭제</Btn><Btn variant="soft" onClick={onClose}>닫기</Btn><Btn onClick={() => onEdit(c)}>수정</Btn></>}>
      <div className="mg-detail-grid">
        <div><div className="k">과목</div><div className="v">{c.subject || '-'}</div></div>
        <div><div className="k">담당 강사</div><div className="v">{t?.name || '미지정'}</div></div>
        <div><div className="k">수업</div><div className="v">{c.days?.length ? c.days.join('·') : '-'} {c.time}</div></div>
        <div><div className="k">강의실</div><div className="v">{c.room || '-'}</div></div>
        <div><div className="k">월 수강료</div><div className="v">{fmtMoney(c.fee)}</div></div>
        <div><div className="k">인원</div><div className="v">{members.length}{c.capacity ? ` / ${c.capacity}` : ''}명</div></div>
      </div>
      {c.memo && <div className="mg-note-box" style={{ marginTop: 14 }}>{c.memo}</div>}
      <div className="mg-sec">수강생 ({members.length}명)</div>
      <div className="mg-toolbar">
        <select className="mg-select grow" value={addId} onChange={(e) => setAddId(e.target.value)}>
          <option value="">학생 추가 선택…</option>
          {candidates.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.school} {s.grade})</option>)}
        </select>
        <Btn variant="ghost" onClick={addStudent} disabled={!addId}>추가</Btn>
      </div>
      {members.length ? (
        <ul className="mg-list">{members.map((s) => (
          <li key={s.id}><span><b>{s.name}</b> <span className="mg-muted">{s.school} {s.grade}</span> {s.status !== '재원' && <Badge tone="amber">{s.status}</Badge>}</span><Btn variant="soft" size="sm" onClick={() => removeStudent(s)}>제외</Btn></li>
        ))}</ul>
      ) : <div className="mg-muted">아직 수강생이 없습니다.</div>}
    </Modal>
  );
}

export default function Classes() {
  const { classes, students, teachers } = useAcademy();
  const [form, setForm] = useState(null);
  const [detail, setDetail] = useState(null);
  const count = (id) => students.filter((s) => s.status === '재원' && (s.classIds || []).includes(id)).length;
  const rows = [...classes].sort((a, b) => a.name.localeCompare(b.name, 'ko'));
  const columns = [
    { key: 'name', label: '반 이름', render: (c) => <b>{c.name}</b> },
    { key: 'subject', label: '과목' },
    { key: 'teacher', label: '담당 강사', render: (c) => teachers.find((t) => t.id === c.teacherId)?.name || <span className="mg-muted">미지정</span> },
    { key: 'days', label: '요일', render: (c) => c.days?.length ? c.days.join('·') : '-' },
    { key: 'time', label: '시간', render: (c) => c.time || '-' },
    { key: 'room', label: '강의실', render: (c) => c.room || '-' },
    { key: 'fee', label: '월 수강료', align: 'r', render: (c) => fmtMoney(c.fee) },
    { key: 'n', label: '인원', align: 'c', render: (c) => { const n = count(c.id); const over = c.capacity && n > c.capacity; return <Badge tone={over ? 'red' : 'navy'}>{n}{c.capacity ? ` / ${c.capacity}` : ''}</Badge>; } },
  ];
  return (
    <>
      <PageHead title="반 · 수업 관리" desc={`운영 중인 반 ${classes.length}개`} right={<Btn onClick={() => setForm({})}>+ 반 만들기</Btn>} />
      <div className="mg-card">
        <Table columns={columns} rows={rows} onRowClick={(c) => setDetail(c.id)}
          empty={<Empty icon="🏫" title="등록된 반이 없습니다." desc="반을 만들고 학생을 배정하면 출결과 수강료가 자동으로 연결됩니다." action={<Btn onClick={() => setForm({})}>+ 반 만들기</Btn>} />} />
        <div className="mg-muted" style={{ marginTop: 8 }}>행을 클릭하면 수강생을 관리할 수 있습니다.</div>
      </div>
      {form && <ClassForm initial={form.id ? form : null} onClose={() => setForm(null)} />}
      {detail && !form && <ClassDetail id={detail} onClose={() => setDetail(null)} onEdit={(c) => setForm(c)} />}
    </>
  );
}

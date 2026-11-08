import { useRef, useState } from 'react';
import { useAcademy, updateSettings, exportJSON, importJSON, loadSample, resetAll, STORAGE_KEY, DEFAULT_SETTINGS } from '../../lib/academyStore';
import { Btn, Field, PageHead, useManage } from './ui';

export default function Settings() {
  const { settings, employees, attendance, leaves, payrolls, contracts } = useAcademy();
  const { notify } = useManage();
  const [f, setF] = useState({ academyName: settings.academyName, workStart: settings.workStart, workEnd: settings.workEnd, defaultAnnualLeave: settings.defaultAnnualLeave });
  const [r, setR] = useState({ ...settings.rates });
  const fileRef = useRef();
  const onImport = async (file) => {
    if (!file) return;
    if (!window.confirm('현재 데이터를 백업 파일 내용으로 덮어씁니다. 계속할까요?')) { fileRef.current.value = ''; return; }
    try { await importJSON(file); notify('백업을 복원했습니다.'); } catch (e) { notify('복원 실패: ' + e.message); }
    fileRef.current.value = '';
  };
  const saveBasic = () => { updateSettings({ academyName: f.academyName.trim() || DEFAULT_SETTINGS.academyName, workStart: f.workStart || '09:00', workEnd: f.workEnd || '18:00', defaultAnnualLeave: Number(f.defaultAnnualLeave) || 0 }); notify('저장했습니다.'); };
  const saveRates = () => { const n = {}; Object.keys(r).forEach((k) => { n[k] = Number(r[k]) || 0; }); updateSettings({ rates: n }); notify('요율을 저장했습니다.'); };
  const rateField = (k, label, help) => <Field label={label} help={help}><input className="mg-input" inputMode="decimal" value={r[k]} onChange={(e) => setR({ ...r, [k]: e.target.value })} /></Field>;
  return (
    <>
      <PageHead title="설정 · 백업" />
      <div className="mg-card">
        <div className="mg-card-title">학원 · 근무 기준</div>
        <div className="mg-form">
          <Field label="학원 이름"><input className="mg-input" value={f.academyName} onChange={(e) => setF({ ...f, academyName: e.target.value })} /></Field>
          <Field label="기본 연차 부여 일수" help="직원 등록 시 기본값. 직원별로 변경 가능"><input className="mg-input" inputMode="numeric" value={f.defaultAnnualLeave} onChange={(e) => setF({ ...f, defaultAnnualLeave: e.target.value })} /></Field>
          <Field label="기준 출근 시각" help="이보다 늦게 출근하면 지각으로 판정"><input type="time" className="mg-input" value={f.workStart} onChange={(e) => setF({ ...f, workStart: e.target.value })} /></Field>
          <Field label="기준 퇴근 시각" help="이보다 일찍 퇴근하면 조퇴로 판정"><input type="time" className="mg-input" value={f.workEnd} onChange={(e) => setF({ ...f, workEnd: e.target.value })} /></Field>
        </div>
        <div style={{ marginTop: 12 }}><Btn onClick={saveBasic}>저장</Btn></div>
      </div>
      <div className="mg-card">
        <div className="mg-card-title">4대보험 · 세율 (근로자 부담분, %)</div>
        <div className="mg-form">
          {rateField('pension', '국민연금')}
          {rateField('health', '건강보험')}
          {rateField('care', '장기요양보험', '건강보험료 대비 비율')}
          {rateField('employment', '고용보험')}
          {rateField('freelancerTax', '프리랜서 원천징수', '사업소득세 3% + 지방소득세 0.3%')}
        </div>
        <div style={{ marginTop: 12, display: 'flex', gap: 8 }}><Btn onClick={saveRates}>요율 저장</Btn><Btn variant="soft" onClick={() => setR({ ...DEFAULT_SETTINGS.rates })}>기본값으로</Btn></div>
        <div className="mg-help" style={{ marginTop: 8 }}>요율은 매년 변경됩니다. 국민연금공단·건강보험공단 고시를 확인해 갱신하세요. 소득세(간이세액)는 급여별로 직접 입력합니다.</div>
      </div>
      <div className="mg-card">
        <div className="mg-card-title">데이터 백업 · 복원</div>
        <p className="mg-muted" style={{ marginBottom: 12 }}>
          모든 데이터는 <b>이 브라우저</b>에만 저장됩니다. 다른 기기에서 보거나 브라우저 데이터를 지우기 전에는 반드시 백업 파일을 내려받으세요.
          <br />현재 저장량: 직원 {employees.length} · 근태 {attendance.length} · 휴가 {leaves.length} · 급여 {payrolls.length} · 계약 {contracts.length}
        </p>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Btn onClick={() => { exportJSON(); notify('백업 파일을 내려받습니다.'); }}>백업 파일 다운로드 (JSON)</Btn>
          <Btn variant="ghost" onClick={() => fileRef.current.click()}>백업 파일 복원</Btn>
          <input ref={fileRef} type="file" accept="application/json,.json" style={{ display: 'none' }} onChange={(e) => onImport(e.target.files[0])} />
        </div>
      </div>
      <div className="mg-card">
        <div className="mg-card-title">샘플 · 초기화</div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Btn variant="soft" onClick={() => { if (window.confirm('현재 데이터를 지우고 샘플 데이터로 바꿀까요?')) { loadSample(); notify('샘플 데이터를 불러왔습니다.'); } }}>샘플 데이터 불러오기</Btn>
          <Btn variant="danger" onClick={() => { if (window.confirm('정말 모든 데이터를 삭제할까요? 되돌릴 수 없습니다.') && window.confirm('마지막 확인: 백업은 받아두셨나요?')) { resetAll(); notify('모든 데이터를 삭제했습니다.'); } }}>모든 데이터 삭제</Btn>
        </div>
        <div className="mg-help" style={{ marginTop: 10 }}>저장 키: {STORAGE_KEY}</div>
      </div>
    </>
  );
}

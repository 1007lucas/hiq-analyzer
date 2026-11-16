import Link from 'next/link';
import FinanceLayout from '../../components/finance/Layout';

const IcAcademy = () => <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M3 10l9-5 9 5-9 5z" /><path d="M7 12.5V17c0 1.5 2.5 3 5 3s5-1.5 5-3v-4.5" /><path d="M21 10v6" /></svg>;
const IcPerson = () => <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></svg>;

export default function FinanceHub() {
  return (
    <FinanceLayout title="홈">
      <div className="hub-hero">
        <h1>어느 비서를 부를까요?</h1>
        <p>은행·카드 거래내역 파일을 올리면 AI가 분류하고, 각 비서가 할 일을 정리해 드립니다.</p>
      </div>
      <div className="hub">
        <Link href="/finance/academy">
          <div className="h-ic a"><IcAcademy /></div>
          <h2>학원 전담 재무 비서</h2>
          <p className="desc">학원 사업용 계좌·카드 내역으로</p>
          <ul>
            <li>수강료 수납·미납 관리 — 입금 자동 대조, 안내 문자 작성</li>
            <li>월 손익 분석과 AI 코멘트</li>
            <li>강사 급여 계산 (3.3% / 4대보험)</li>
            <li>세금·신고 일정 알림 (원천세·사업장현황·종소세)</li>
          </ul>
          <span className="go">학원 비서 시작하기 →</span>
        </Link>
        <Link href="/finance/personal">
          <div className="h-ic b"><IcPerson /></div>
          <h2>개인 전담 재무 비서</h2>
          <p className="desc">개인 계좌·카드 내역으로</p>
          <ul>
            <li>지출 분류·월 리포트와 AI 절약 제안</li>
            <li>카테고리별 예산 설정·초과 경고</li>
            <li>저축·목표 추적</li>
            <li>고정지출·구독 자동 점검</li>
          </ul>
          <span className="go">개인 비서 시작하기 →</span>
        </Link>
      </div>
      <div className="steps">
        <div className="step"><div className="n">1</div><div><b>파일 올리기</b><span>은행·카드사에서 받은 엑셀/CSV를 드래그하면 열을 자동으로 인식합니다.</span></div></div>
        <div className="step"><div className="n">2</div><div><b>자동 분류</b><span>키워드 규칙과 AI가 카테고리를 정하고, 직접 고치면 다음부터 기억합니다.</span></div></div>
        <div className="step"><div className="n">3</div><div><b>비서에게 맡기기</b><span>수납·급여·세무 또는 예산·목표·구독을 매달 점검합니다. 데이터는 내 브라우저에만 저장됩니다.</span></div></div>
      </div>
    </FinanceLayout>
  );
}

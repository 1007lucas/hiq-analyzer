import Head from 'next/head';
import Link from 'next/link';
import { useRouter } from 'next/router';
import { useEffect, useState } from 'react';

export const FINANCE_CSS = `
:root{
  --primary:#3B6CF6;--primary-dk:#2F5CE0;--primary-soft:#EEF2FF;--primary-text:#2451D9;
  --ink:#191F28;--ink2:#333D4B;--gray:#6B7684;--gray2:#8B95A1;--graylt:#F2F4F6;--border:#E5E8EB;--border2:#EEF0F3;
  --bg:#F4F6F9;--white:#fff;--paper:#F8F9FB;
  --green:#0B8A5F;--greenfaint:#E9F9F1;--red:#E5335B;--redfaint:#FFF0F3;--amber:#9A5B00;--amberfaint:#FFF7E6;
  --navy:#191F28;--navy2:#191F28;--navylt:#333D4B;--gold:#F59E0B;--goldl:#FCD34D;--goldfaint:#FFF7E6;
  --series-1:#3B6CF6;--series-2:#1BAF7A;--seq-200:#C7D4FD;--seq-450:#3B6CF6;--seq-600:#2451D9;
  --status-good:#0B8A5F;--status-warn:#F59E0B;--status-bad:#E5335B;
  --radius:16px;--shadow:0 1px 2px rgba(16,24,40,.04),0 1px 3px rgba(16,24,40,.03);
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
html{-webkit-text-size-adjust:100%;}
body{font-family:Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',sans-serif;background:var(--bg);color:var(--ink);min-height:100vh;line-height:1.6;font-size:14px;-webkit-font-smoothing:antialiased;}
button,input,select,textarea{font-family:inherit;}
a{color:inherit;}
header.fin{background:rgba(255,255,255,.92);backdrop-filter:saturate(180%) blur(10px);border-bottom:1px solid var(--border2);padding:0 24px;display:flex;align-items:center;justify-content:space-between;height:64px;position:sticky;top:0;z-index:100;}
.logo{display:flex;align-items:center;gap:11px;text-decoration:none;color:var(--ink);}
.logo-mark{width:36px;height:36px;border-radius:11px;background:linear-gradient(135deg,#3B6CF6 0%,#7B9BFF 100%);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:15px;color:#fff;letter-spacing:-.02em;box-shadow:0 4px 10px rgba(59,108,246,.25);}
.logo-text{font-weight:800;font-size:16px;line-height:1.15;letter-spacing:-.01em;}
.logo-sub{color:var(--gray2);font-size:11.5px;font-weight:500;display:block;margin-top:3px;}
.topnav{display:flex;gap:2px;background:var(--graylt);padding:4px;border-radius:999px;}
.topnav a{color:var(--gray);text-decoration:none;font-size:13.5px;font-weight:600;padding:7px 14px;border-radius:999px;transition:all .15s;}
.topnav a.active{color:var(--ink);background:#fff;box-shadow:0 1px 3px rgba(16,24,40,.1);}
.topnav a:hover:not(.active){color:var(--ink);}
.main{max-width:1080px;margin:0 auto;padding:32px 24px 100px;}
.page-head{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:14px;margin-bottom:20px;}
.page-head h1{font-size:24px;font-weight:800;letter-spacing:-.02em;line-height:1.25;}
.page-head .eyebrow{font-size:13px;color:var(--gray);font-weight:600;margin-bottom:4px;letter-spacing:.01em;}
.page-head .sub{font-size:13.5px;color:var(--gray);margin-top:6px;}
.card{background:#fff;border:1px solid var(--border2);border-radius:var(--radius);padding:24px;margin-bottom:16px;box-shadow:var(--shadow);}
.card-title{font-weight:700;font-size:16px;letter-spacing:-.01em;margin-bottom:16px;display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;}
.card-title small{font-weight:500;color:var(--gray2);font-size:12.5px;margin-left:8px;}
.subtabs{display:inline-flex;gap:2px;background:var(--graylt);padding:4px;border-radius:12px;margin-bottom:22px;max-width:100%;overflow-x:auto;}
.subtab{padding:8px 16px;font-size:14px;font-weight:600;color:var(--gray);cursor:pointer;border-radius:9px;white-space:nowrap;display:inline-flex;align-items:center;transition:all .15s;user-select:none;}
.subtab:hover{color:var(--ink);}
.subtab.active{color:var(--ink);background:#fff;box-shadow:0 1px 3px rgba(16,24,40,.1);}
.subtab .cnt{display:inline-flex;align-items:center;justify-content:center;margin-left:7px;min-width:18px;height:18px;font-size:11px;font-weight:700;background:var(--red);color:#fff;padding:0 5px;border-radius:999px;}
.btn{padding:10px 16px;font-size:14px;font-weight:600;cursor:pointer;border:none;border-radius:10px;white-space:nowrap;transition:all .15s;display:inline-flex;align-items:center;gap:7px;line-height:1.2;}
.btn-primary{background:var(--primary);color:#fff;box-shadow:0 2px 6px rgba(59,108,246,.25);}
.btn-primary:hover{background:var(--primary-dk);}
.btn-primary:disabled{background:#B9C7F5;box-shadow:none;cursor:not-allowed;}
.btn-ghost{background:var(--graylt);color:var(--ink2);}
.btn-ghost:hover{background:#E8EBEF;}
.btn-ghost:disabled{opacity:.5;cursor:not-allowed;}
.btn-danger{background:var(--redfaint);color:var(--red);}
.btn-danger:hover{background:#FFE1E8;}
.btn-sm{padding:7px 12px;font-size:13px;border-radius:8px;}
.btn-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;}
.btn-copy{background:var(--graylt);color:var(--ink2);border:none;cursor:pointer;padding:7px 12px;font-size:13px;font-weight:600;border-radius:8px;}
.btn-copy:hover{background:#E8EBEF;}
input[type=text],input[type=number],input[type=date],input[type=month],select,textarea{padding:9px 12px;border:1px solid var(--border);background:#fff;border-radius:10px;font-size:14px;color:var(--ink);transition:border-color .15s,box-shadow .15s;}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--primary);box-shadow:0 0 0 3px rgba(59,108,246,.15);}
input::placeholder{color:#B0B8C1;}
select{appearance:none;max-width:100%;padding-right:30px;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%238B95A1' stroke-width='1.6' fill='none' stroke-linecap='round'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 11px center;}
input[type=checkbox]{width:16px;height:16px;accent-color:var(--primary);vertical-align:-3px;margin-right:6px;}
label.fl{display:block;font-size:12.5px;font-weight:600;color:var(--gray);margin-bottom:6px;}
.field{display:flex;flex-direction:column;}
.panel{background:var(--paper);border:1px solid var(--border2);border-radius:14px;padding:18px 20px;margin-top:20px;}
.panel-title{font-size:13.5px;font-weight:700;color:var(--ink2);margin-bottom:12px;}
.grid{display:grid;gap:12px;}
.grid>*{min-width:0;}
.card{min-width:0;}
.g2{grid-template-columns:1fr 1fr;} .g3{grid-template-columns:repeat(3,1fr);} .g4{grid-template-columns:repeat(4,1fr);}
.grid.g2>.card,.grid.g3>.card,.grid.g4>.card{margin-bottom:0;}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px;}
.stats.c3{grid-template-columns:repeat(3,1fr);}
.stat{background:#fff;border:1px solid var(--border2);border-radius:var(--radius);padding:20px 22px;box-shadow:var(--shadow);}
.stat .lbl{font-size:13px;color:var(--gray);font-weight:600;}
.stat .val{font-size:26px;font-weight:800;color:var(--ink);margin-top:6px;letter-spacing:-.025em;font-variant-numeric:tabular-nums;line-height:1.2;white-space:nowrap;}
.stat .val.neg{color:var(--red);} .stat .val.pos{color:var(--green);}
.stat .delta{display:inline-flex;align-items:center;gap:4px;white-space:nowrap;max-width:100%;margin-top:10px;font-size:12px;font-weight:600;color:var(--gray);background:var(--graylt);padding:3px 9px;border-radius:999px;}
.stat .delta.bad{color:var(--red);background:var(--redfaint);} .stat .delta.good{color:var(--green);background:var(--greenfaint);}
.meter-list{display:flex;flex-direction:column;gap:13px;}
.mrow{display:grid;grid-template-columns:150px 1fr 130px;gap:14px;align-items:center;font-size:14px;}
.mrow .nm{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink2);}
.mrow .trk{height:8px;background:var(--graylt);position:relative;border-radius:999px;}
.mrow .bar{position:absolute;left:0;top:0;height:100%;background:var(--seq-450);border-radius:999px;transition:width .4s ease;}
.mrow .bar.over{background:var(--status-bad);}
.mrow .bar.warn{background:var(--status-warn);}
.mrow .bar.income{background:var(--series-2);}
.mrow .lim{position:absolute;top:-4px;width:2px;height:16px;background:var(--ink);border-radius:2px;}
.mrow .v{min-width:0;text-align:right;font-variant-numeric:tabular-nums;font-weight:600;}
.mrow .v small{display:block;color:var(--gray2);font-size:11.5px;font-weight:500;}
.tbl-wrap{border:1px solid var(--border2);border-radius:12px;overflow:auto;}
table.tbl{width:100%;border-collapse:collapse;font-size:14px;}
.tbl th{text-align:left;font-size:12px;color:var(--gray);font-weight:600;padding:10px 12px;background:var(--paper);border-bottom:1px solid var(--border2);white-space:nowrap;}
.tbl td{padding:10px 12px;border-bottom:1px solid var(--border2);vertical-align:middle;}
.tbl tr:last-child td{border-bottom:none;}
.tbl td.num,.tbl th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;}
.tbl tbody tr:hover td{background:#FAFBFD;}
.tbl .neg{color:var(--red);} .tbl .pos{color:var(--green);}
.tbl select,.tbl input{padding:6px 9px;font-size:13px;border-radius:8px;}
.tbl select{padding-right:26px;}
.chip{display:inline-flex;align-items:center;font-size:12px;font-weight:600;padding:3px 9px;border-radius:999px;background:var(--primary-soft);color:var(--primary-text);white-space:nowrap;line-height:1.4;}
.chip.red{background:var(--redfaint);color:var(--red);} .chip.green{background:var(--greenfaint);color:var(--green);} .chip.amber{background:var(--amberfaint);color:var(--amber);} .chip.gray{background:var(--graylt);color:var(--gray);}
.drop-zone{border:2px dashed #D6DBE2;border-radius:16px;padding:36px 20px;text-align:center;cursor:pointer;background:var(--paper);transition:all .2s;}
.drop-zone:hover,.drop-zone.over{border-color:var(--primary);background:var(--primary-soft);}
.drop-ic{width:56px;height:56px;border-radius:16px;background:var(--primary-soft);color:var(--primary);display:flex;align-items:center;justify-content:center;margin:0 auto 12px;}
.note{font-size:13px;color:var(--gray);line-height:1.6;}
.banner{padding:12px 16px;font-size:13.5px;margin-bottom:14px;border-radius:12px;background:var(--primary-soft);color:var(--primary-text);line-height:1.55;}
.banner.warn{background:var(--amberfaint);color:var(--amber);}
.banner.err{background:var(--redfaint);color:var(--red);}
.banner.ok{background:var(--greenfaint);color:var(--green);}
.ai-box{background:linear-gradient(135deg,#F3F6FF 0%,#FAF7FF 100%);border:1px solid #E6EAFB;border-radius:14px;padding:20px 22px;font-size:14.5px;white-space:pre-wrap;line-height:1.8;color:var(--ink2);}
.month-nav{display:inline-flex;align-items:center;gap:4px;background:#fff;border:1px solid var(--border);border-radius:999px;padding:4px;}
.month-nav button{background:transparent;border:none;width:32px;height:32px;border-radius:50%;cursor:pointer;font-size:18px;color:var(--gray);display:flex;align-items:center;justify-content:center;}
.month-nav button:hover{background:var(--graylt);color:var(--ink);}
.month-nav .cur{font-weight:700;min-width:116px;text-align:center;font-size:15px;letter-spacing:-.01em;}
.toast{position:fixed;bottom:28px;left:50%;transform:translateX(-50%);background:var(--ink);color:#fff;padding:12px 20px;font-size:14px;font-weight:600;border-radius:12px;box-shadow:0 12px 32px rgba(16,24,40,.25);z-index:999;pointer-events:none;}
.spinner{width:14px;height:14px;border:2px solid rgba(255,255,255,.3);border-top-color:#fff;border-radius:50%;animation:spin .7s linear infinite;display:inline-block;}
.spinner.dark{border-color:rgba(59,108,246,.25);border-top-color:var(--primary);}
@keyframes spin{to{transform:rotate(360deg)}}
.empty{display:flex;flex-direction:column;align-items:center;text-align:center;padding:36px 20px;gap:10px;}
.empty .ic{width:56px;height:56px;border-radius:16px;background:var(--graylt);display:flex;align-items:center;justify-content:center;color:var(--gray2);}
.empty p{font-size:14px;color:var(--gray);max-width:420px;line-height:1.65;}
.hub-hero{text-align:center;padding:16px 0 32px;}
.hub-hero h1{font-size:30px;font-weight:800;letter-spacing:-.03em;line-height:1.25;}
.hub-hero p{color:var(--gray);font-size:15px;margin-top:10px;}
.hub{display:grid;grid-template-columns:1fr 1fr;gap:16px;}
.hub a{display:flex;flex-direction:column;text-decoration:none;color:inherit;background:#fff;border:1px solid var(--border2);border-radius:20px;padding:30px;box-shadow:var(--shadow);transition:transform .18s,box-shadow .18s,border-color .18s;}
.hub a:hover{transform:translateY(-3px);box-shadow:0 14px 34px rgba(16,24,40,.1);border-color:#D6DEFF;}
.hub .h-ic{width:56px;height:56px;border-radius:16px;display:flex;align-items:center;justify-content:center;margin-bottom:18px;color:#fff;}
.hub .h-ic.a{background:linear-gradient(135deg,#3B6CF6,#7B9BFF);} .hub .h-ic.b{background:linear-gradient(135deg,#1BAF7A,#5BD3A8);}
.hub h2{font-size:20px;font-weight:800;letter-spacing:-.02em;margin-bottom:6px;}
.hub .desc{font-size:14px;color:var(--gray);margin-bottom:18px;}
.hub ul{list-style:none;display:flex;flex-direction:column;gap:9px;margin-bottom:22px;}
.hub ul li{font-size:14px;color:var(--ink2);display:flex;gap:9px;align-items:flex-start;line-height:1.5;}
.hub ul li::before{content:'';flex:none;width:18px;height:18px;margin-top:2px;border-radius:50%;background:var(--greenfaint) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='8' viewBox='0 0 10 8'%3E%3Cpath d='M1 4l2.5 2.5L9 1' stroke='%230B8A5F' stroke-width='1.8' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") center no-repeat;}
.hub .go{margin-top:auto;font-weight:700;color:var(--primary);font-size:14px;}
.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:28px;}
.step{background:#fff;border:1px solid var(--border2);border-radius:14px;padding:18px 20px;display:flex;gap:12px;align-items:flex-start;}
.step .n{flex:none;width:26px;height:26px;border-radius:8px;background:var(--primary-soft);color:var(--primary-text);font-weight:800;font-size:13px;display:flex;align-items:center;justify-content:center;}
.step b{display:block;font-size:14px;margin-bottom:2px;}
.step span{font-size:13px;color:var(--gray);line-height:1.5;}
.row-actions{display:flex;gap:6px;}
.muted{color:var(--gray2);}
.right{text-align:right;}
.sticky-sum{position:sticky;bottom:0;background:var(--paper);border-top:1px solid var(--border2);padding:12px 16px;font-weight:600;font-size:13.5px;display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;}
.legend{display:flex;gap:16px;font-size:12.5px;color:var(--gray);align-items:center;font-weight:500;}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px;}
.tip{position:absolute;background:var(--ink);color:#fff;font-size:12.5px;padding:8px 11px;border-radius:9px;pointer-events:none;white-space:nowrap;z-index:5;transform:translate(-50%,-110%);line-height:1.5;box-shadow:0 6px 18px rgba(16,24,40,.2);}
.list-row{display:grid;gap:14px;padding:14px 0;border-bottom:1px solid var(--border2);}
.list-row:last-child{border-bottom:none;}
.dday{font-weight:800;font-size:17px;letter-spacing:-.02em;}
.dday.soon{color:var(--red);}
@media(max-width:760px){header.fin{padding:0 14px;height:58px;}.logo-sub{display:none;}.topnav a{padding:6px 11px;font-size:13px;}.main{padding:20px 14px 80px;}.page-head h1{font-size:21px;}.stats,.stats.c3{grid-template-columns:1fr 1fr;}.g3,.g4{grid-template-columns:1fr 1fr;}.hub{grid-template-columns:1fr;}.steps{grid-template-columns:1fr;}.mrow{grid-template-columns:1fr;gap:5px;}.mrow .v{text-align:left;}.card{padding:18px;border-radius:14px;}.stat{padding:16px 18px;}.stat .val{font-size:20px;white-space:normal;overflow-wrap:anywhere;}.subtabs{width:100%;}}
@media(max-width:480px){.g2,.g3,.g4{grid-template-columns:1fr;}.stats,.stats.c3{grid-template-columns:1fr 1fr;}.stat .val{font-size:18px;}.stat .delta span{display:none;}.stat .delta{font-size:11.5px;padding:3px 7px;}}
`;

export default function FinanceLayout({ title, children, active }) {
  const router = useRouter();
  const path = router?.pathname || '';
  const is = (p) => (active ? active === p : path === p);
  return (
    <>
      <Head>
        <title>{title ? `${title} · HIQ 재무 비서` : 'HIQ 재무 비서'}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css" />
      </Head>
      <style dangerouslySetInnerHTML={{ __html: FINANCE_CSS }} />
      <header className="fin">
        <Link href="/finance" className="logo">
          <div className="logo-mark">H</div>
          <div className="logo-text">재무 비서<span className="logo-sub">HIQ · 학원 · 개인</span></div>
        </Link>
        <nav className="topnav">
          <Link href="/finance/academy" className={is('/finance/academy') ? 'active' : ''}>학원</Link>
          <Link href="/finance/personal" className={is('/finance/personal') ? 'active' : ''}>개인</Link>
          <Link href="/">지문 분석기</Link>
        </nav>
      </header>
      <div className="main">{children}</div>
    </>
  );
}

export function useToast() {
  const [toast, setToast] = useState('');
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(''), 2800);
    return () => clearTimeout(t);
  }, [toast]);
  const el = toast ? <div className="toast">{toast}</div> : null;
  return [setToast, el];
}

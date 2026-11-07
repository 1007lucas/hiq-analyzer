// HIQ 인사 관리 시스템 - 데스크톱(Electron) 진입점
// Next.js 정적 빌드(out/)를 app:// 커스텀 프로토콜로 서빙해 서버 없이 실행합니다.
const { app, BrowserWindow, Menu, protocol, net, shell, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const { pathToFileURL } = require('url');

const isDev = !app.isPackaged;
const OUT_DIR = isDev ? path.join(__dirname, '..', 'out') : path.join(process.resourcesPath, 'out');
const APP_NAME = 'HIQ 인사 관리 시스템';

protocol.registerSchemesAsPrivileged([
  { scheme: 'app', privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true } },
]);

function resolveFile(urlPath) {
  let p = decodeURIComponent(urlPath.split('?')[0].split('#')[0]);
  if (p.endsWith('/')) p += 'index.html';
  let file = path.normalize(path.join(OUT_DIR, p));
  if (!file.startsWith(OUT_DIR)) return null; // 경로 탈출 방지
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
  if (!fs.existsSync(file) && fs.existsSync(file + '.html')) file += '.html';
  if (!fs.existsSync(file)) return path.join(OUT_DIR, '404.html');
  return file;
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1360,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    title: APP_NAME,
    backgroundColor: '#F8F7F3',
    autoHideMenuBar: false,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  win.loadURL('app://-/manage/');
  // 외부 링크는 기본 브라우저로
  win.webContents.setWindowOpenHandler(({ url }) => { if (/^https?:/.test(url)) shell.openExternal(url); return { action: 'deny' }; });
  win.webContents.on('will-navigate', (e, url) => { if (/^https?:/.test(url)) { e.preventDefault(); shell.openExternal(url); } });
  win.on('page-title-updated', (e) => e.preventDefault());
  // 자동 테스트용: HR_SMOKE=<png 경로> 이면 화면을 캡처하고 종료
  if (process.env.HR_SMOKE) {
    win.webContents.on('did-finish-load', () => setTimeout(async () => {
      const img = await win.webContents.capturePage();
      fs.writeFileSync(process.env.HR_SMOKE, img.toPNG());
      const title = await win.webContents.executeJavaScript('document.querySelector(".mg-page-title")?.textContent || "NO_PAGE"');
      console.log('SMOKE_TITLE=' + title);
      app.quit();
    }, 2500));
  }
  return win;
}

function buildMenu(win) {
  const template = [
    {
      label: '파일',
      submenu: [
        { label: '백업 파일 다운로드', accelerator: 'CmdOrCtrl+S', click: () => win.webContents.executeJavaScript(`window.location.hash='settings'; window.dispatchEvent(new HashChangeEvent('hashchange'));`) },
        { label: '인쇄', accelerator: 'CmdOrCtrl+P', click: () => win.webContents.print() },
        { type: 'separator' },
        { label: '데이터 저장 폴더 열기', click: () => shell.openPath(app.getPath('userData')) },
        { type: 'separator' },
        { role: 'quit', label: '종료' },
      ],
    },
    {
      label: '보기',
      submenu: [
        { role: 'reload', label: '새로고침' },
        { type: 'separator' },
        { role: 'zoomIn', label: '확대' }, { role: 'zoomOut', label: '축소' }, { role: 'resetZoom', label: '원래 크기' },
        { type: 'separator' },
        { role: 'togglefullscreen', label: '전체 화면' },
        ...(isDev ? [{ type: 'separator' }, { role: 'toggleDevTools', label: '개발자 도구' }] : []),
      ],
    },
    {
      label: '도움말',
      submenu: [
        { label: '사용 안내', click: () => dialog.showMessageBox(win, { type: 'info', title: APP_NAME, message: APP_NAME, detail: '직원 정보 → 계약 → 근태/휴가 → 급여 순서로 사용하세요.\n\n모든 데이터는 이 컴퓨터에만 저장됩니다. 설정 · 백업 메뉴에서 주기적으로 백업 파일을 내려받으세요.\n\n데이터 저장 위치:\n' + app.getPath('userData') }) },
        { label: `버전 ${app.getVersion()}`, enabled: false },
      ],
    },
  ];
  if (process.platform === 'darwin') template.unshift({ label: app.name, submenu: [{ role: 'about', label: `${APP_NAME} 정보` }, { type: 'separator' }, { role: 'hide', label: '숨기기' }, { role: 'quit', label: '종료' }] });
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

app.setName(APP_NAME);
app.whenReady().then(() => {
  protocol.handle('app', (request) => {
    const { pathname } = new URL(request.url);
    const file = resolveFile(pathname);
    if (!file) return new Response('Forbidden', { status: 403 });
    return net.fetch(pathToFileURL(file).toString());
  });
  // 백업 파일 다운로드 시 저장 위치 묻기
  const { session } = require('electron');
  session.defaultSession.on('will-download', (e, item) => {
    item.setSaveDialogOptions({ title: '백업 파일 저장', defaultPath: path.join(app.getPath('documents'), item.getFilename()) });
  });
  const win = createWindow();
  buildMenu(win);
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) buildMenu(createWindow()); });
});
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });

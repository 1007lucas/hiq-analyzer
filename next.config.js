/** @type {import('next').NextConfig} */
const isDesktop = process.env.DESKTOP_BUILD === '1';

const nextConfig = {
  reactStrictMode: true,
  env: { NEXT_PUBLIC_DESKTOP: isDesktop ? '1' : '' },
  // 데스크톱(Electron) 빌드: 정적 파일로 내보내어 서버 없이 실행
  ...(isDesktop ? { output: 'export', distDir: 'out', trailingSlash: true, images: { unoptimized: true } } : {}),
};
module.exports = nextConfig;

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 개발 서버가 각 백엔드로 대신 전달해 준다 (CORS 걱정 없음)
//   /svc/deficit   → 녹지 부족지수   (8000)
//   /svc/candidate → 후보지 추천     (8001)
//   /svc/design    → 녹지 설계       (8002)
//   /svc/ai        → AI 토지 피복    (8003)
//   /esri          → Esri 위성사진 내보내기 (AI 에 보낼 항공사진)
const svc = (port) => ({
  target: `http://127.0.0.1:${port}`,
  changeOrigin: true,
  rewrite: (p) => p.replace(/^\/svc\/[^/]+/, ''),
})

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/svc/deficit': svc(8000),
      '/svc/candidate': svc(8001),
      '/svc/design': svc(8002),
      '/svc/ai': { ...svc(8003), timeout: 180000, proxyTimeout: 180000 },
      '/esri': {
        target: 'https://server.arcgisonline.com',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/esri/, ''),
      },
    },
  },
})

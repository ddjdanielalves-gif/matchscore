import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Backend port. Defaults to 8001 to avoid clashing with other apps on 8000.
const apiPort = process.env.VITE_API_PORT ?? '8001'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": `http://127.0.0.1:${apiPort}`,
    },
  },
})

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development, /api goes to the FastAPI server (uvicorn capcraft_api.main:app --port 8000).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
})

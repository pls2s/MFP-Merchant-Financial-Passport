import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Share the repository-root .env with the backend; only VITE_* variables reach the browser.
  envDir: '..',
})

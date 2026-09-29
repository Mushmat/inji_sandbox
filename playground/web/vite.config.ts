import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// `npm run dev` serves the UI on 5173 and forwards /api to the BFF on 5050.
// `npm run build` writes dist/, which the BFF serves itself on 5050.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { '/api': 'http://127.0.0.1:5050' },
  },
})

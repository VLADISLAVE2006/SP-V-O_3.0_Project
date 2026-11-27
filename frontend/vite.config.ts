import path from 'node:path'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const variablesPath = path
  .resolve(path.dirname(fileURLToPath(import.meta.url)), 'src/styles/variables.scss')
  .replaceAll('\\', '/')

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  css: {
    preprocessorOptions: {
      scss: {
        additionalData: (source, filename) => {
          if (filename.replaceAll('\\', '/').endsWith('/src/styles/variables.scss')) {
            return source
          }
          return `@use "${variablesPath}" as *;\n${source}`
        },
      },
    },
  },
})

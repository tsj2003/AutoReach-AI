import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://localhost:8080',
      '/login': {
        target: 'http://localhost:8080',
        bypass: (req, res, options) => {
          if (req.method === 'GET' && req.headers.accept?.includes('text/html')) {
            return '/index.html';
          }
        }
      },
      '/signup': {
        target: 'http://localhost:8080',
        bypass: (req, res, options) => {
          if (req.method === 'GET' && req.headers.accept?.includes('text/html')) {
            return '/index.html';
          }
        }
      },
      '/dashboard': {
        target: 'http://localhost:8080',
        bypass: (req, res, options) => {
          if (req.method === 'GET' && req.headers.accept?.includes('text/html')) {
            return '/index.html';
          }
        }
      },
      '/privacy': {
        target: 'http://localhost:8080',
        bypass: (req, res, options) => {
          if (req.method === 'GET' && req.headers.accept?.includes('text/html')) {
            return '/index.html';
          }
        }
      },
      '/terms': {
        target: 'http://localhost:8080',
        bypass: (req, res, options) => {
          if (req.method === 'GET' && req.headers.accept?.includes('text/html')) {
            return '/index.html';
          }
        }
      },
      '/refund-policy': {
        target: 'http://localhost:8080',
        bypass: (req, res, options) => {
          if (req.method === 'GET' && req.headers.accept?.includes('text/html')) {
            return '/index.html';
          }
        }
      },
      '/contact': {
        target: 'http://localhost:8080',
        bypass: (req, res, options) => {
          if (req.method === 'GET' && req.headers.accept?.includes('text/html')) {
            return '/index.html';
          }
        }
      },
      '/logout': 'http://localhost:8080',
    }
  },
  build: {
    outDir: '../app/static',
    emptyOutDir: false,
    rollupOptions: {
      output: {
        entryFileNames: 'assets/index.js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name].[ext]'
      }
    }
  }
})


FROM node:20-alpine

WORKDIR /app

# Install dependencies first for better layer caching
COPY package*.json ./
RUN npm install

# Copy source code
COPY . .

# Patch vite.config.ts to add server proxy and host binding so the Vite dev
# server can be reached from Docker networking and proxy /api to the API container.
# API_URL is a server-side env var (no VITE_ prefix) so it is NOT exposed to the
# browser bundle — the browser always uses relative /api paths through this proxy.
RUN cat > vite.config.ts << 'EOF'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: process.env.API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
EOF

EXPOSE 5173

CMD ["npm", "run", "dev"]

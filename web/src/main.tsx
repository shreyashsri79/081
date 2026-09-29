import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Fonts are bundled, never fetched at runtime: the venue network is not trusted.
import '@fontsource-variable/source-serif-4/opsz.css'
import '@fontsource-variable/geist/index.css'
import '@fontsource/ibm-plex-mono/latin-400.css'
import '@fontsource/ibm-plex-mono/latin-500.css'
import './index.css'
import App from './App.tsx'

const queries = new QueryClient({
  defaultOptions: { queries: { staleTime: Infinity, retry: false, refetchOnWindowFocus: false } },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queries}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)

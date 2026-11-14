import { Toaster } from 'sonner'
import { Shell } from './shell/Shell.tsx'

export default function App() {
  return (
    <>
      <Shell />
      <Toaster position="top-center" offset={60} toastOptions={{ unstyled: true, classNames: { toast: 'toast', title: 'toast-title', description: 'toast-desc' } }} />
    </>
  )
}

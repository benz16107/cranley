import { useEffect } from 'react'
import { Toaster, toast } from 'sonner'
import { onNotice } from '../../core/index.ts'
import { Shell } from './shell/Shell.tsx'

export default function App() {
  // what core has to tell the person arrives as a notice; in this look it is a toast
  useEffect(() => onNotice((n) => (n.kind === 'error' ? toast.error : toast)(n.title, { description: n.description })), [])
  return (
    <>
      <Shell />
      <Toaster position="bottom-right" offset={16} mobileOffset={12} toastOptions={{ unstyled: true, classNames: { toast: 'toast', title: 'toast-title', description: 'toast-desc' } }} />
    </>
  )
}

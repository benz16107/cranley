import { useEffect } from 'react'
import { Toaster, toast } from 'sonner'
import { onNotice } from '../../core/index.ts'
import { Shell } from './shell/Shell.tsx'

export default function App() {
  // what core has to tell the person arrives as a notice; in this look it is a toast
  // (core words one notice for a look with the brief on the left; here the question is in the agent panel)
  useEffect(() => onNotice((n) => (n.kind === 'error' ? toast.error : toast)(n.title, { description: n.description?.replace('in the brief, on the left', 'in the agent panel') })), [])
  return (
    <>
      <Shell />
      <Toaster position="bottom-center" offset={30} mobileOffset={30} toastOptions={{ unstyled: true, classNames: { toast: 'toast', title: 'toast-title', description: 'toast-desc' } }} />
    </>
  )
}

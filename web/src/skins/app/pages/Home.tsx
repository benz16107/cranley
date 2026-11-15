import { compose, useWorkspace } from '../../../core/index.ts'
import { Ask } from '../home/Ask.tsx'
import { FirstAsk } from '../home/FirstAsk.tsx'
import { Setup } from '../home/Setup.tsx'
import { STATUS, Work } from '../home/Work.tsx'
import { started, useSeen } from '../lib/pending.ts'
import { useKnown } from '../shell/Knows.tsx'
import './home.css'

export { STATUS }

/** The field and needs inside the guided first run's dialog (shell/FirstRun.tsx). Home itself uses `<Ask>`. */
export function Composer({ onStart = compose }: { first?: boolean; bare?: boolean; onStart?: (sentence: string, needId?: string) => unknown }) {
  return <FirstAsk onStart={onStart} />
}

/** Home: one entry (say what you need, about any building or one), then the person's own work. While a brief is
    being set up, its tools and questions take the entry's place. Parts are in `../home/`. */
export function Home() {
  const doc = useWorkspace((s) => s.doc)
  const seen = useSeen((s) => s.all)
  const known = useKnown()
  const composing = !!doc.brief && doc.plan.length === 0 && doc.panels.length === 0
  const returning = known > 0 || Object.keys(seen).length > 0
  return (
    <div className="page home">
      <div className="inner" data-composing={composing || undefined}>
        {composing ? <Setup /> : <Ask first={!started(doc) && !returning} returning={returning} />}
        <Work doc={doc} composing={composing} />
      </div>
    </div>
  )
}

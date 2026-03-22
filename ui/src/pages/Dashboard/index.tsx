import { useStore } from '../../store/useStore'
import { Navbar } from '../../components/layout/Navbar'
import { PreferencesModal } from '../../components/layout/PreferencesModal'
import { Match } from './Match'
import { AgentLog } from './AgentLog'

export function DashboardPage() {
  const { topTab } = useStore()

  return (
    <div className="h-screen flex flex-col bg-zinc-950 overflow-hidden">
      <Navbar />
      <main className="flex-1 overflow-hidden">
        {topTab === 'match' && <Match />}
        {topTab === 'agent' && <AgentLog />}
      </main>
      <PreferencesModal />
    </div>
  )
}

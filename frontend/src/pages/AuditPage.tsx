import { useState, useMemo } from 'react'
import { Download, Filter } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { AuditTable } from '@/components/AuditTable'
import { useWorkflows, useWorkflowAudit } from '@/hooks/useWorkflows'

const ALL_SENTINEL = '__all__'

export function AuditPage() {
  const { data: workflows } = useWorkflows()
  const [selectedWorkflow, setSelectedWorkflow] = useState<string>('')
  const [filterText, setFilterText] = useState('')

  const { data: records, isLoading } = useWorkflowAudit(selectedWorkflow)

  const filtered = useMemo(() => {
    if (!records) return []
    const q = filterText.toLowerCase()
    return records.filter(
      (r) =>
        r.variable.toLowerCase().includes(q) ||
        r.action.toLowerCase().includes(q) ||
        r.agent.toLowerCase().includes(q),
    )
  }, [records, filterText])

  function handleDownload() {
    if (!records) return
    const blob = new Blob([JSON.stringify(records, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `audit-${selectedWorkflow}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="p-8">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Audit Trail</h1>
          <p className="mt-1 text-sm text-slate-500">
            Immutable log of all derivation and QC actions
          </p>
        </div>
        {records && records.length > 0 && (
          <Button variant="outline" size="sm" className="gap-1.5" onClick={handleDownload}>
            <Download size={14} />
            Export JSON
          </Button>
        )}
      </div>

      {/* Controls */}
      <div className="mb-4 flex gap-3">
        <Select
          value={selectedWorkflow}
          onValueChange={(v) => setSelectedWorkflow(v === ALL_SENTINEL || v === null ? '' : v)}
        >
          <SelectTrigger className="w-72">
            <SelectValue placeholder="Select a workflow…" />
          </SelectTrigger>
          <SelectContent>
            {workflows?.map((w) => (
              <SelectItem key={w.workflow_id} value={w.workflow_id}>
                <span className="font-mono text-xs">{w.workflow_id.slice(0, 16)}…</span>
                <span className="ml-2 text-slate-400">({w.status})</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {selectedWorkflow && (
          <div className="relative flex-1 max-w-xs">
            <Filter size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input
              className="pl-8"
              placeholder="Filter by variable, action, agent…"
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
            />
          </div>
        )}
      </div>

      {/* Table */}
      {!selectedWorkflow && (
        <div className="rounded-lg border border-dashed border-slate-300 py-16 text-center text-slate-400">
          Select a workflow to view its audit trail
        </div>
      )}

      {selectedWorkflow && isLoading && (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-10 animate-pulse rounded bg-slate-200" />
          ))}
        </div>
      )}

      {selectedWorkflow && !isLoading && <AuditTable records={filtered} />}
    </div>
  )
}

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Play, FileCode, ChevronDown, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useSpecs, useStartWorkflow } from '@/hooks/useWorkflows'
import { api } from '@/lib/api'

export function SpecsPage() {
  const navigate = useNavigate()
  const { data: specs, isLoading, error } = useSpecs()
  const { mutate: startWorkflow, isPending, variables: pendingSpec } = useStartWorkflow()
  const [expanded, setExpanded] = useState<string | null>(null)
  const [yamlContent, setYamlContent] = useState<Record<string, string>>({})

  function handleRun(filename: string) {
    startWorkflow(filename, {
      onSuccess: (data) => navigate(`/workflows/${data.workflow_id}`),
    })
  }

  async function toggleExpand(filename: string) {
    if (expanded === filename) {
      setExpanded(null)
      return
    }
    setExpanded(filename)
    if (!yamlContent[filename]) {
      const content = await api.getSpecContent(filename)
      setYamlContent((prev) => ({ ...prev, [filename]: content }))
    }
  }

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-slate-900">Transformation Specs</h1>
        <p className="mt-1 text-sm text-slate-500">
          YAML specifications defining SDTM-to-ADaM derivation rules
        </p>
      </div>

      {isLoading && (
        <div className="space-y-2">
          {[1, 2].map((i) => (
            <div key={i} className="h-12 animate-pulse rounded bg-slate-200" />
          ))}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          Failed to load specs. Ensure the backend is running.
        </div>
      )}

      {specs && specs.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 py-16 text-center">
          <FileCode size={32} className="mb-3 text-slate-300" />
          <p className="text-slate-500">No spec files found.</p>
          <p className="mt-1 text-xs text-slate-400">Add YAML specs to the specs/ directory.</p>
        </div>
      )}

      {specs && specs.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          <Table>
            <TableHeader>
              <TableRow className="bg-slate-50">
                <TableHead className="w-10" />
                <TableHead className="w-48">Study</TableHead>
                <TableHead>Description</TableHead>
                <TableHead className="w-32 text-right">Derivations</TableHead>
                <TableHead className="w-28 text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {specs.map((spec) => (
                <>
                  <TableRow
                    key={spec.filename}
                    className="cursor-pointer hover:bg-slate-50"
                    onClick={() => void toggleExpand(spec.filename)}
                  >
                    <TableCell className="w-10 px-3 text-slate-400">
                      {expanded === spec.filename ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </TableCell>
                    <TableCell>
                      <div>
                        <p className="font-medium text-slate-800">{spec.study}</p>
                        <p className="text-xs text-slate-400">{spec.filename}</p>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-slate-600">{spec.description}</TableCell>
                    <TableCell className="text-right text-sm font-medium text-slate-700">
                      {spec.derivation_count}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        className="gap-1.5 text-xs"
                        disabled={isPending && pendingSpec === spec.filename}
                        onClick={(e) => { e.stopPropagation(); handleRun(spec.filename) }}
                      >
                        <Play size={12} />
                        {isPending && pendingSpec === spec.filename ? 'Starting…' : 'Run'}
                      </Button>
                    </TableCell>
                  </TableRow>
                  {expanded === spec.filename && (
                    <TableRow key={`${spec.filename}-yaml`}>
                      <TableCell colSpan={5} className="p-0">
                        <pre
                          className="overflow-y-auto whitespace-pre-wrap break-words bg-slate-950 p-4 text-xs leading-relaxed text-emerald-300"
                          style={{ fontFamily: "'JetBrains Mono', monospace", maxHeight: 400 }}
                        >
                          {yamlContent[spec.filename] ?? 'Loading...'}
                        </pre>
                      </TableCell>
                    </TableRow>
                  )}
                </>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

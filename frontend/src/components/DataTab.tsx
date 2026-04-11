import { useState } from 'react'
import { Download, ChevronDown, ChevronRight, Table2, Columns3 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import type { DataPreviewResponse, DatasetPreview } from '@/types/api'

type DataTabProps = {
  workflowId: string
  data: DataPreviewResponse | undefined
  isLoading: boolean
}

function formatCell(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const str = String(value)
  return str.length > 40 ? str.slice(0, 40) + '…' : str
}

function DtypeBadge({ dtype }: { dtype: string }) {
  const colors: Record<string, string> = {
    'int64': 'bg-blue-50 text-blue-700 border-blue-200',
    'float64': 'bg-violet-50 text-violet-700 border-violet-200',
    'object': 'bg-slate-50 text-slate-600 border-slate-200',
    'bool': 'bg-amber-50 text-amber-700 border-amber-200',
    'datetime64': 'bg-emerald-50 text-emerald-700 border-emerald-200',
  }
  const cls = colors[dtype] ?? 'bg-slate-50 text-slate-600 border-slate-200'
  return (
    <span className={`inline-block rounded border px-1.5 py-0.5 text-[10px] font-medium leading-none ${cls}`}>
      {dtype}
    </span>
  )
}

function DatasetPanel({ dataset }: { dataset: DatasetPreview }) {
  const [showSchema, setShowSchema] = useState(false)
  const columnsWithNulls = dataset.columns.filter((c) => c.null_count > 0).length

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      {/* Header bar */}
      <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/50 px-5 py-3.5">
        <div className="flex items-center gap-3">
          <Table2 size={16} className="text-slate-400" />
          <div>
            <h3 className="text-sm font-semibold text-slate-800">{dataset.label}</h3>
            <p className="mt-0.5 text-xs text-slate-500">
              {dataset.row_count.toLocaleString()} rows &times; {dataset.column_count} columns
              {columnsWithNulls > 0 && (
                <span className="ml-1.5 text-amber-600">
                  &middot; {columnsWithNulls} col{columnsWithNulls !== 1 ? 's' : ''} with nulls
                </span>
              )}
            </p>
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="gap-1.5 text-xs text-slate-500 hover:text-slate-700"
          onClick={() => setShowSchema(!showSchema)}
        >
          <Columns3 size={13} />
          Schema
          {showSchema ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        </Button>
      </div>

      {/* Collapsible schema section */}
      {showSchema && (
        <div className="border-b border-slate-100 bg-slate-50/30 px-5 py-3">
          <div className="grid grid-cols-[minmax(0,1fr)] gap-px overflow-hidden rounded-lg border border-slate-200 bg-slate-200 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {dataset.columns.map((col) => (
              <div key={col.name} className="flex items-center justify-between bg-white px-3 py-2">
                <div className="flex items-center gap-2 overflow-hidden">
                  <span className="truncate text-xs font-medium text-slate-700">{col.name}</span>
                  <DtypeBadge dtype={col.dtype} />
                </div>
                {col.null_count > 0 && (
                  <span className="ml-2 shrink-0 text-[10px] tabular-nums text-amber-600">
                    {col.null_count.toLocaleString()} null{col.null_count !== 1 ? 's' : ''}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Data table */}
      <div className="overflow-x-auto">
        <table className="w-full min-w-max text-xs">
          <thead>
            <tr className="sticky top-0 z-10 border-b border-slate-200 bg-slate-50">
              <th className="sticky left-0 z-20 bg-slate-50 px-3 py-2.5 text-right text-[10px] font-normal tabular-nums text-slate-400 w-12">
                #
              </th>
              {dataset.columns.map((col) => (
                <th
                  key={col.name}
                  className="whitespace-nowrap px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500"
                >
                  {col.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {dataset.rows.map((row, i) => (
              <tr
                key={i}
                className={`border-b border-slate-50 transition-colors hover:bg-blue-50/40 ${
                  i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'
                }`}
              >
                <td className="sticky left-0 z-10 bg-inherit px-3 py-1.5 text-right text-[10px] tabular-nums text-slate-300">
                  {i + 1}
                </td>
                {dataset.columns.map((col) => (
                  <td
                    key={col.name}
                    className="whitespace-nowrap px-3 py-1.5 font-mono text-[11px] text-slate-700"
                  >
                    {formatCell(row[col.name])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Footer with showing count */}
      <div className="border-t border-slate-100 bg-slate-50/50 px-5 py-2 text-xs text-slate-400">
        Showing {Math.min(dataset.rows.length, 50)} of {dataset.row_count.toLocaleString()} rows
      </div>
    </div>
  )
}

export function DataTab({ workflowId, data, isLoading }: DataTabProps) {
  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="h-10 w-56 animate-pulse rounded-lg bg-slate-200" />
        <div className="h-80 animate-pulse rounded-xl bg-slate-100" />
      </div>
    )
  }

  const hasData = data?.source != null || data?.derived != null

  if (!hasData) {
    return (
      <div className="rounded-xl border border-dashed border-slate-200 py-20 text-center text-sm text-slate-400">
        Data not yet available
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Download toolbar */}
      {data.derived_formats.length > 0 && (
        <div className="flex items-center gap-3">
          <span className="text-xs font-medium uppercase tracking-wider text-slate-400">Export</span>
          <div className="h-4 w-px bg-slate-200" />
          {data.derived_formats.includes('csv') && (
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 rounded-lg text-xs"
              onClick={() => void api.downloadAdam(workflowId, 'csv')}
            >
              <Download size={13} />
              CSV
            </Button>
          )}
          {data.derived_formats.includes('parquet') && (
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 rounded-lg text-xs"
              onClick={() => void api.downloadAdam(workflowId, 'parquet')}
            >
              <Download size={13} />
              Parquet
            </Button>
          )}
        </div>
      )}

      {/* Dataset panels */}
      <div className="space-y-6">
        {data.source != null && <DatasetPanel dataset={data.source} />}
        {data.derived != null && <DatasetPanel dataset={data.derived} />}
      </div>
    </div>
  )
}

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { AuditRecord } from '@/types/api'

type AuditTableProps = {
  records: AuditRecord[]
}

export function AuditTable({ records }: AuditTableProps) {
  if (records.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-slate-300 py-16 text-center text-slate-400">
        No audit records yet
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <Table>
        <TableHeader>
          <TableRow className="bg-slate-50">
            <TableHead className="w-44">Timestamp</TableHead>
            <TableHead className="w-32">Variable</TableHead>
            <TableHead className="w-32">Action</TableHead>
            <TableHead className="w-32">Agent</TableHead>
            <TableHead>Details</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {records.map((r, i) => (
            <TableRow key={i} className="text-sm hover:bg-slate-50">
              <TableCell className="font-mono text-xs text-slate-500">
                {new Date(r.timestamp).toLocaleString()}
              </TableCell>
              <TableCell className="font-medium text-slate-800">{r.variable}</TableCell>
              <TableCell className="text-slate-600">{r.action}</TableCell>
              <TableCell className="text-slate-600">{r.agent}</TableCell>
              <TableCell className="max-w-xs truncate font-mono text-xs text-slate-400">
                {JSON.stringify(r.details)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

// Module-level position cache — persists across component unmounts within the page lifetime.
// Key: `${workflowId}:${nodeId}` — Value: { x, y }
// Cleared on full page reload; survives tab switches (Radix UI Tabs unmounts inactive content).
const dagPositionCache = new Map<string, { x: number; y: number }>()

export function getCachedPosition(
  workflowId: string,
  nodeId: string,
): { x: number; y: number } | undefined {
  return dagPositionCache.get(`${workflowId}:${nodeId}`)
}

export function setCachedPosition(
  workflowId: string,
  nodeId: string,
  pos: { x: number; y: number },
): void {
  dagPositionCache.set(`${workflowId}:${nodeId}`, pos)
}

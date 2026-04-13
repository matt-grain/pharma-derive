import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ApprovalDialog } from '@/components/ApprovalDialog'
import type { DAGNode, ApprovalRequest } from '@/types/api'

const FIXTURE_VARIABLES: DAGNode[] = [
  {
    variable: 'AGEGR1',
    status: 'approved',
    layer: 1,
    coder_code: 'def derive_agegr1(df): return df["AGE"].apply(lambda x: "<65" if x < 65 else ">=65")',
    qc_code: 'def derive_agegr1(df): return df["AGE"].apply(lambda x: "<65" if x < 65 else ">=65")',
    qc_verdict: 'match',
    approved_code: 'def derive_agegr1(df): return df["AGE"].apply(lambda x: "<65" if x < 65 else ">=65")',
    dependencies: [],
    source_columns: [{ name: 'AGE', domain: 'dm' }],
  },
  {
    variable: 'RACEN',
    status: 'approved',
    layer: 1,
    coder_code: 'def derive_racen(df): return df["RACE"].map(RACE_MAP)',
    qc_code: 'def derive_racen(df): return df["RACE"].map(RACE_MAP)',
    qc_verdict: 'match',
    approved_code: 'def derive_racen(df): return df["RACE"].map(RACE_MAP)',
    dependencies: [],
    source_columns: [{ name: 'RACE', domain: 'dm' }],
  },
  {
    variable: 'TRTEDT',
    status: 'approved',
    layer: 2,
    coder_code: 'def derive_trtedt(df): return pd.to_datetime(df["RFXENDTC"])',
    qc_code: null,
    qc_verdict: null,
    approved_code: 'def derive_trtedt(df): return pd.to_datetime(df["RFXENDTC"])',
    dependencies: ['TRTSDTM'],
    source_columns: [{ name: 'RFXENDTC', domain: 'ex' }],
  },
]

function renderApprovalDialog(overrides: Partial<React.ComponentProps<typeof ApprovalDialog>> = {}) {
  const props = {
    open: true,
    onOpenChange: vi.fn(),
    variables: FIXTURE_VARIABLES,
    onConfirm: vi.fn(),
    isApproving: false,
    ...overrides,
  }
  return { ...render(<ApprovalDialog {...props} />), props }
}

describe('ApprovalDialog', () => {
  it('should default all variables to approved', () => {
    // Arrange + Act
    renderApprovalDialog()

    // Assert — all 3 checkboxes should be checked by default
    const checkboxes = screen.getAllByRole('checkbox')
    expect(checkboxes).toHaveLength(3)
    checkboxes.forEach((cb) => {
      expect(cb).toBeChecked()
    })
  })

  it('should toggle a variable when its checkbox is clicked', async () => {
    // Arrange
    const user = userEvent.setup()
    renderApprovalDialog()
    const checkboxes = screen.getAllByRole('checkbox')
    const firstCheckbox = checkboxes[0]

    // Act
    await user.click(firstCheckbox!)

    // Assert
    expect(firstCheckbox).not.toBeChecked()
    // Other checkboxes remain checked
    expect(checkboxes[1]).toBeChecked()
    expect(checkboxes[2]).toBeChecked()
  })

  it('should send per-variable decisions on confirm', async () => {
    // Arrange
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    renderApprovalDialog({ onConfirm })

    // Act — uncheck the second variable then confirm
    const checkboxes = screen.getAllByRole('checkbox')
    await user.click(checkboxes[1]!)
    await user.click(screen.getByRole('button', { name: /approve & run audit/i }))

    // Assert
    expect(onConfirm).toHaveBeenCalledOnce()
    const payload = onConfirm.mock.calls[0]?.[0] as ApprovalRequest
    expect(payload.variables).toHaveLength(3)
    const agegr1 = payload.variables.find((v) => v.variable === 'AGEGR1')
    const racen = payload.variables.find((v) => v.variable === 'RACEN')
    expect(agegr1?.approved).toBe(true)
    expect(racen?.approved).toBe(false)
  })
})

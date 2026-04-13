import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RejectDialog } from '@/components/RejectDialog'

function renderRejectDialog(overrides: Partial<React.ComponentProps<typeof RejectDialog>> = {}) {
  const props = {
    open: true,
    onOpenChange: vi.fn(),
    onConfirm: vi.fn(),
    isRejecting: false,
    ...overrides,
  }
  return { ...render(<RejectDialog {...props} />), props }
}

describe('RejectDialog', () => {
  it('should render when open', () => {
    // Arrange + Act
    renderRejectDialog()

    // Assert
    expect(screen.getByText('Reject Workflow')).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toBeInTheDocument()
  })

  it('should disable confirm when reason is empty', () => {
    // Arrange + Act
    renderRejectDialog()

    // Assert
    const confirmButton = screen.getByRole('button', { name: /confirm rejection/i })
    expect(confirmButton).toBeDisabled()
  })

  it('should enable confirm when reason has content', async () => {
    // Arrange
    const user = userEvent.setup()
    renderRejectDialog()

    // Act
    await user.type(screen.getByRole('textbox'), 'QC mismatch unresolved')

    // Assert
    expect(screen.getByRole('button', { name: /confirm rejection/i })).not.toBeDisabled()
  })

  it('should call onConfirm with trimmed reason', async () => {
    // Arrange
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    renderRejectDialog({ onConfirm })

    // Act
    await user.type(screen.getByRole('textbox'), '  QC mismatch unresolved  ')
    await user.click(screen.getByRole('button', { name: /confirm rejection/i }))

    // Assert
    expect(onConfirm).toHaveBeenCalledOnce()
    expect(onConfirm).toHaveBeenCalledWith('QC mismatch unresolved')
  })

  it('should show Rejecting... when isRejecting is true', () => {
    // Arrange + Act
    renderRejectDialog({ isRejecting: true })

    // Assert
    expect(screen.getByRole('button', { name: /rejecting/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /rejecting/i })).toBeDisabled()
  })
})

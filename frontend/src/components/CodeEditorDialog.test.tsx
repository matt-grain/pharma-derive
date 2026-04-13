import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CodeEditorDialog } from '@/components/CodeEditorDialog'

const INITIAL_CODE = 'def derive_agegr1(df):\n    return df["AGE"].apply(lambda x: "<65" if x < 65 else ">=65")'

function renderCodeEditorDialog(overrides: Partial<React.ComponentProps<typeof CodeEditorDialog>> = {}) {
  const props = {
    open: true,
    onOpenChange: vi.fn(),
    variable: 'AGEGR1',
    currentCode: INITIAL_CODE,
    onSave: vi.fn(),
    isSaving: false,
    error: null,
    ...overrides,
  }
  return { ...render(<CodeEditorDialog {...props} />), props }
}

describe('CodeEditorDialog', () => {
  it('should pre-fill code from props', () => {
    // Arrange + Act
    renderCodeEditorDialog()

    // Assert — the code textarea should contain the initial code
    const codeTextarea = screen.getByLabelText('Code')
    expect(codeTextarea).toHaveValue(INITIAL_CODE)
  })

  it('should disable save when code unchanged', () => {
    // Arrange + Act
    renderCodeEditorDialog()

    // Assert — code unchanged and reason empty → disabled
    expect(screen.getByRole('button', { name: /save override/i })).toBeDisabled()
  })

  it('should disable save when reason empty', async () => {
    // Arrange
    const user = userEvent.setup()
    renderCodeEditorDialog()

    // Act — change the code but leave reason empty
    const codeTextarea = screen.getByLabelText('Code')
    await user.clear(codeTextarea)
    await user.type(codeTextarea, 'def derive_agegr1(df): return "new"')

    // Assert — still disabled because reason is empty
    expect(screen.getByRole('button', { name: /save override/i })).toBeDisabled()
  })

  it('should display error when error prop is set', () => {
    // Arrange + Act
    renderCodeEditorDialog({ error: '400: Invalid Python syntax' })

    // Assert
    expect(screen.getByText('400: Invalid Python syntax')).toBeInTheDocument()
  })

  it('should call onSave with new code and reason', async () => {
    // Arrange
    const user = userEvent.setup()
    const onSave = vi.fn()
    renderCodeEditorDialog({ onSave })

    // Act
    const codeTextarea = screen.getByLabelText('Code')
    await user.clear(codeTextarea)
    await user.type(codeTextarea, 'def derive_agegr1(df): return "patched"')

    const reasonTextarea = screen.getByLabelText(/reason for change/i)
    await user.type(reasonTextarea, 'Fixed boundary condition')

    await user.click(screen.getByRole('button', { name: /save override/i }))

    // Assert
    expect(onSave).toHaveBeenCalledOnce()
    expect(onSave).toHaveBeenCalledWith(
      'def derive_agegr1(df): return "patched"',
      'Fixed boundary condition',
    )
  })
})

import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import OperatorsPage from "@/app/admin/rag/operators/page"
import { ragAdminService } from "@/services"
import { useTenant } from "@/contexts/TenantContext"

// Mocks
jest.mock("@/services", () => ({
    ragAdminService: {
        listCustomOperators: jest.fn(),
        createCustomOperator: jest.fn(),
        updateCustomOperator: jest.fn(),
        deleteCustomOperator: jest.fn(),
        testCustomOperator: jest.fn(),
    },
}))

jest.mock("@/contexts/TenantContext", () => ({
    useTenant: jest.fn(),
}))

jest.mock("@/components/ui/code-editor", () => ({
    CodeEditor: ({ value, onChange }: any) => (
        <textarea
            data-testid="code-editor"
            value={value}
            onChange={(e) => onChange(e.target.value)}
        />
    ),
}))

// Mock Next.js router
const mockPush = jest.fn()
const mockGet = jest.fn()
jest.mock("next/navigation", () => ({
    useRouter: () => ({
        push: mockPush,
    }),
    useSearchParams: () => ({
        get: mockGet,
    }),
}))

describe("OperatorsPage", () => {
    const mockTenant = { slug: "test-tenant", name: "Test Tenant" }
    const mockOperators = [
        {
            id: "op-1",
            name: "test_op",
            display_name: "Test Operator",
            category: "custom",
            input_type: "raw_documents",
            output_type: "raw_documents",
            python_code: "def execute(context): return []",
            version: "1.0",
            updated_at: new Date().toISOString(),
        },
    ]

    beforeEach(() => {
        jest.clearAllMocks()
            ; (useTenant as jest.Mock).mockReturnValue({ currentTenant: mockTenant })
            ; (ragAdminService.listCustomOperators as jest.Mock).mockResolvedValue(mockOperators)
        mockGet.mockReturnValue(null) // default for searchParams
    })

    it("renders the operators list correctly", async () => {
        render(<OperatorsPage />)

        expect(await screen.findByText("Test Operator")).toBeInTheDocument()
        expect(screen.getByText("Custom Operators")).toBeInTheDocument()
    })

    it("navigates to create mode on new operator click", async () => {
        render(<OperatorsPage />)

        const createBtn = await screen.findByText("New Operator")
        fireEvent.click(createBtn)

        expect(screen.getByPlaceholderText("My Custom Operator")).toBeInTheDocument()
        expect(screen.getByTestId("code-editor")).toBeInTheDocument()
    })

    it("creates a new operator", async () => {
        ; (ragAdminService.createCustomOperator as jest.Mock).mockResolvedValue({
            ...mockOperators[0],
            id: "new-op",
        })

        render(<OperatorsPage />)

        // Go to create mode
        fireEvent.click(await screen.findByText("New Operator"))

        // Fill form
        fireEvent.change(screen.getByPlaceholderText("My Custom Operator"), {
            target: { value: "New Op" },
        })

        // Save
        fireEvent.click(screen.getByText("Save"))

        await waitFor(() => {
            expect(ragAdminService.createCustomOperator).toHaveBeenCalledWith(
                expect.objectContaining({
                    display_name: "New Op",
                    name: "new_op",
                }),
                "test-tenant"
            )
        })
    })

    it("deletes an operator", async () => {
        window.confirm = jest.fn(() => true) // Mock confirm dialog
        render(<OperatorsPage />)

        const deleteBtn = (await screen.findAllByRole("button")).find((btn) =>
            btn.querySelector("svg.text-destructive")
        )

        if (deleteBtn) {
            fireEvent.click(deleteBtn)
        } else {
            throw new Error("Delete button not found")
        }

        await waitFor(() => {
            expect(ragAdminService.deleteCustomOperator).toHaveBeenCalledWith(
                "op-1",
                "test-tenant"
            )
        })
    })

    describe("Slug Logic", () => {
        it("auto-generates slug from display name", async () => {
            render(<OperatorsPage />)
            fireEvent.click(await screen.findByText("New Operator"))

            const nameInput = screen.getByPlaceholderText("My Custom Operator")
            const slugInput = screen.getByPlaceholderText("my_custom_operator")

            fireEvent.change(nameInput, { target: { value: "My New Operator" } })
            expect(slugInput).toHaveValue("my_new_operator")
        })

        it("locks slug when manually edited", async () => {
            render(<OperatorsPage />)
            fireEvent.click(await screen.findByText("New Operator"))

            const nameInput = screen.getByPlaceholderText("My Custom Operator")
            const slugInput = screen.getByPlaceholderText("my_custom_operator")

            // Manually edit slug
            fireEvent.change(slugInput, { target: { value: "manual_slug" } })

            // Change name
            fireEvent.change(nameInput, { target: { value: "Something Else" } })

            // Slug should remain locked
            expect(slugInput).toHaveValue("manual_slug")
        })

        it("shows error on slug collision", async () => {
            render(<OperatorsPage />)
            fireEvent.click(await screen.findByText("New Operator"))

            const slugInput = screen.getByPlaceholderText("my_custom_operator")

            // test_op is already in mockOperators
            fireEvent.change(slugInput, { target: { value: "test_op" } })

            expect(await screen.findByText("Slug already exists")).toBeInTheDocument()
        })
    })

    it("executes a test run", async () => {
        ; (ragAdminService.testCustomOperator as jest.Mock).mockResolvedValue({
            success: true,
            data: ["output"],
            execution_time_ms: 10,
        })

        render(<OperatorsPage />)

        // Go to edit mode
        const editBtn = (await screen.findAllByRole("button")).find((btn) =>
            btn.querySelector("svg.lucide-edit") || btn.innerHTML.includes("Edit")
        )
        if (editBtn) fireEvent.click(editBtn)
        else {
            // Fallback if edit icon check fails, just go to create
            fireEvent.click(await screen.findByText("New Operator"))
        }

        // Open test panel
        const consoleBtn = await screen.findByText("Test Console")
        fireEvent.click(consoleBtn)

        expect(screen.getByText("Run Test")).toBeInTheDocument()

        // Run test
        fireEvent.click(screen.getByText("Run Test"))

        await waitFor(() => {
            expect(ragAdminService.testCustomOperator).toHaveBeenCalled()
            expect(screen.getByText("Output Data")).toBeInTheDocument()
        })
    })
})

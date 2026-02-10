"use client"

import { ReactNode } from "react"
import {
    Trash2,
    Undo2,
    Redo2,
    MousePointer2,
    Hand,
    Save,
    Zap,
    Play,
    Loader2,
    LayoutPanelLeft,
    LayoutGrid,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/utils"

export type InteractionMode = "pan" | "select"

interface ToolbarButtonProps {
    icon: ReactNode
    onClick: () => void
    disabled?: boolean
    active?: boolean
    variant?: "default" | "destructive" | "save" | "compile" | "run"
    title: string
    loading?: boolean
}

/**
 * Individual toolbar button with consistent styling and color variants.
 */
export function ToolbarButton({
    icon,
    onClick,
    disabled,
    active,
    variant = "default",
    title,
    loading
}: ToolbarButtonProps) {
    const variantClasses = {
        default: "",
        destructive: "text-destructive hover:text-destructive hover:bg-destructive/10",
        save: "text-blue-500 hover:text-blue-600 hover:bg-blue-500/10",
        compile: "text-orange-500 hover:text-orange-600 hover:bg-orange-500/10",
        run: "text-green-500 hover:text-green-600 hover:bg-green-500/10",
    }

    return (
        <Button
            variant="ghost"
            size="icon"
            className={cn(
                "rounded-xl h-10 w-10",
                active && "bg-muted",
                variantClasses[variant]
            )}
            onClick={onClick}
            disabled={disabled || loading}
            title={title}
        >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}
        </Button>
    )
}

interface BuilderToolbarProps {
    // Interaction mode
    interactionMode: InteractionMode
    onModeChange: (mode: InteractionMode) => void

    // History
    canUndo: boolean
    canRedo: boolean
    onUndo: () => void
    onRedo: () => void

    // Actions
    onSave?: () => void
    onCompile?: () => void
    onRun?: () => void
    onAutoLayout?: () => void
    onClear: () => void

    // Loading states
    isSaving?: boolean
    isCompiling?: boolean
    autoLayoutDisabled?: boolean
}

/**
 * Shared toolbar for builder UIs with pan/select, undo/redo, and action buttons.
 */
export function BuilderToolbar({
    interactionMode,
    onModeChange,
    canUndo,
    canRedo,
    onUndo,
    onRedo,
    onSave,
    onCompile,
    onRun,
    onAutoLayout,
    onClear,
    isSaving,
    isCompiling,
    autoLayoutDisabled,
}: BuilderToolbarProps) {
    return (
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 p-1.5 bg-background/90 backdrop-blur-md border rounded-2xl">
            {/* Interaction Mode Toggle */}
            <ToolbarButton
                icon={<Hand className="h-4 w-4" />}
                onClick={() => onModeChange("pan")}
                active={interactionMode === "pan"}
                title="Pan Tool"
            />
            <ToolbarButton
                icon={<MousePointer2 className="h-4 w-4" />}
                onClick={() => onModeChange("select")}
                active={interactionMode === "select"}
                title="Selection Tool"
            />

            <Separator orientation="vertical" className="h-6" />

            {/* History Controls */}
            <ToolbarButton
                icon={<Undo2 className="h-4 w-4" />}
                onClick={onUndo}
                disabled={!canUndo}
                title="Undo"
            />
            <ToolbarButton
                icon={<Redo2 className="h-4 w-4" />}
                onClick={onRedo}
                disabled={!canRedo}
                title="Redo"
            />

            <Separator orientation="vertical" className="h-6" />

            {/* Action Buttons */}
            {onSave && (
                <ToolbarButton
                    icon={<Save className="h-4 w-4" />}
                    onClick={onSave}
                    variant="save"
                    title="Save"
                    loading={isSaving}
                />
            )}

            {onCompile && (
                <ToolbarButton
                    icon={<Zap className="h-4 w-4" />}
                    onClick={onCompile}
                    variant="compile"
                    title="Compile"
                    loading={isCompiling}
                />
            )}

            {onRun && (
                <ToolbarButton
                    icon={<Play className="h-4 w-4" />}
                    onClick={onRun}
                    variant="run"
                    title="Run"
                />
            )}

            {onAutoLayout && (
                <ToolbarButton
                    icon={<LayoutGrid className="h-4 w-4" />}
                    onClick={onAutoLayout}
                    disabled={autoLayoutDisabled}
                    title="Auto Layout"
                />
            )}

            <Separator orientation="vertical" className="h-6" />

            {/* Destructive Actions */}
            <ToolbarButton
                icon={<Trash2 className="h-4 w-4" />}
                onClick={onClear}
                variant="destructive"
                title="Clear Canvas"
            />
        </div>
    )
}

interface CatalogToggleButtonProps {
    visible: boolean
    onClick: () => void
    isExecutionMode?: boolean
}

/**
 * Button to show/hide the catalog panel.
 */
export function CatalogToggleButton({ visible, onClick, isExecutionMode }: CatalogToggleButtonProps) {
    if (visible) return null

    return (
        <div className="absolute left-3 top-3 z-50">
            <Button
                variant="ghost"
                size="icon"
        className="h-10 w-10 rounded-xl shadow-xs bg-background hover:bg-muted"
                onClick={onClick}
                title={isExecutionMode ? "Exit Execution Mode" : "Show Catalog"}
            >
                <LayoutPanelLeft className="h-4 w-4" />
            </Button>
        </div>
    )
}

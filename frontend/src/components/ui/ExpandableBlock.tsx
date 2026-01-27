
"use client"

import React, { useState } from "react"
import { Maximize2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog"
import { cn } from "@/lib/utils"

interface ExpandableBlockProps {
    title: string
    children: React.ReactNode
    renderExpanded?: () => React.ReactNode
    className?: string
    contentClassName?: string
}

export function ExpandableBlock({
    title,
    children,
    renderExpanded,
    className,
    contentClassName,
}: ExpandableBlockProps) {
    const [isExpanded, setIsExpanded] = useState(false)

    return (
        <>
            <div className={cn("relative group border rounded-lg bg-background overflow-hidden w-full min-w-0", className)}>
                <div className="flex items-center justify-between px-3 py-1 bg-muted/40 border-b">
                    <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                        {title}
                    </span>
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
                        onClick={() => setIsExpanded(true)}
                        title="Expand"
                    >
                        <Maximize2 className="h-3.5 w-3.5" />
                    </Button>
                </div>
                <div className={cn("p-0 overflow-auto", contentClassName)}>
                    {children}
                </div>
            </div>

            <Dialog open={isExpanded} onOpenChange={setIsExpanded}>
                <DialogContent className="max-w-[95vw] w-full h-[90vh] flex flex-col p-0 gap-0">
                    <DialogHeader className="px-6 py-2 border-b flex flex-row items-center justify-between space-y-0">
                        <DialogTitle className="text-md font-semibold">{title}</DialogTitle>
                        {/* Built-in close button of Dialog handles closing, but we can add actions here if needed */}
                    </DialogHeader>
                    <div className="flex-1 overflow-auto p-6 bg-muted/10">
                        {renderExpanded ? renderExpanded() : children}
                    </div>
                </DialogContent>
            </Dialog>
        </>
    )
}

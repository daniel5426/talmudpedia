"use client"

import { useEffect, useState } from "react"
import { Check, Search, X, Database } from "lucide-react"
import { cn } from "@/lib/utils"
import { Input } from "@/components/ui/input"
import { knowledgeStoresService, KnowledgeStore } from "@/services"
import { useTenant } from "@/contexts/TenantContext"

interface KnowledgeStoreSelectProps {
    value: string
    onChange: (value: string) => void
    placeholder?: string
    className?: string
}

export function KnowledgeStoreSelect({
    value,
    onChange,
    placeholder = "Select a knowledge store...",
    className
}: KnowledgeStoreSelectProps) {
    const [stores, setStores] = useState<KnowledgeStore[]>([])
    const [loading, setLoading] = useState(true)
    const [showSuggestions, setShowSuggestions] = useState(false)
    const [query, setQuery] = useState("")
    const [selectedIndex, setSelectedIndex] = useState(0)
    const [isFocused, setIsFocused] = useState(false)

    const { currentTenant } = useTenant()

    useEffect(() => {
        async function loadStores() {
            try {
                setLoading(true)
                const data = await knowledgeStoresService.list(currentTenant?.slug)
                setStores(data)
            } catch (error) {
                console.error("Failed to load knowledge stores:", error)
            } finally {
                setLoading(false)
            }
        }
        loadStores()
    }, [currentTenant?.slug])

    // Get the label for the current value
    const selectedStore = stores.find(s => s.id === value)

    // Sync query when value changes and we are not typing
    useEffect(() => {
        if (!isFocused) {
            setQuery(selectedStore?.name || value || "")
        }
    }, [value, selectedStore, isFocused])

    const isValid = !value || !!selectedStore || stores.length === 0 && loading

    const filteredStores = stores.filter(s =>
        s.name.toLowerCase().includes(query.toLowerCase()) ||
        s.id.toLowerCase().includes(query.toLowerCase())
    )

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (!showSuggestions || filteredStores.length === 0) return

        if (e.key === "ArrowDown") {
            e.preventDefault()
            setSelectedIndex(i => (i + 1) % filteredStores.length)
        } else if (e.key === "ArrowUp") {
            e.preventDefault()
            setSelectedIndex(i => (i - 1 + filteredStores.length) % filteredStores.length)
        } else if (e.key === "Enter" || e.key === "Tab") {
            e.preventDefault()
            const selected = filteredStores[selectedIndex]
            if (selected) {
                onChange(selected.id)
                setQuery(selected.name)
                setShowSuggestions(false)
            }
        } else if (e.key === "Escape") {
            setShowSuggestions(false)
        }
    }

    const handleBlur = () => {
        setIsFocused(false)

        // Check if what was typed matches a store exactly (by name or ID)
        const exactMatch = stores.find(s =>
            s.name.toLowerCase() === query.trim().toLowerCase() ||
            s.id.toLowerCase() === query.trim().toLowerCase()
        )

        if (exactMatch) {
            onChange(exactMatch.id)
            setQuery(exactMatch.name)
        } else if (query.trim() === "") {
            onChange("")
            setQuery("")
        } else {
            // It's invalid, but we set it anyway to show the error
            onChange(query.trim())
        }

        // Close suggestions immediately
        setShowSuggestions(false)
    }

    return (
        <div className="relative">
            <div className="relative">
                <Input
                    value={query}
                    onChange={(e) => {
                        setQuery(e.target.value)
                        setShowSuggestions(true)
                    }}
                    onFocus={() => {
                        setIsFocused(true)
                        setShowSuggestions(true)
                    }}
                    onKeyDown={handleKeyDown}
                    placeholder={loading ? "Loading stores..." : placeholder}
                    className={cn(
                        "h-9 px-3 bg-muted/40 border-none rounded-lg text-[13px] focus-visible:ring-1 focus-visible:ring-offset-0 placeholder:text-muted-foreground/40 font-mono pr-8 transition-all",
                        !isValid && "ring-1 ring-destructive bg-destructive/5",
                        className
                    )}
                    onBlur={handleBlur}
                />
                <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
                    {query && (
                        <button
                            className="text-muted-foreground/40 hover:text-muted-foreground"
                            onClick={() => {
                                setQuery("")
                                onChange("")
                            }}
                        >
                            <X className="h-3 w-3" />
                        </button>
                    )}
                    <Database className="h-3.5 w-3.5 text-muted-foreground/30" />
                </div>
            </div>

            {showSuggestions && filteredStores.length > 0 && (
                <div className="absolute z-50 w-full mt-1 bg-popover text-popover-foreground shadow-md rounded-md border border-border p-1 max-h-[200px] overflow-auto">
                    {filteredStores.map((store, idx) => (
                        <div
                            key={store.id}
                            className={cn(
                                "flex flex-col px-2 py-1.5 text-xs rounded-sm cursor-pointer",
                                idx === selectedIndex ? "bg-accent text-accent-foreground" : "hover:bg-muted"
                            )}
                            onMouseDown={(e) => {
                                e.preventDefault() // Prevent blurring the input
                                onChange(store.id)
                                setQuery(store.name)
                                setShowSuggestions(false)
                            }}
                        >
                            <div className="flex items-center justify-between">
                                <span className="font-medium">{store.name}</span>
                                {store.id === value && <Check className="h-3 w-3 text-primary" />}
                            </div>
                            <div className="flex items-center gap-2 text-[10px] opacity-50 font-mono truncate">
                                <span>{store.id}</span>
                                <span>•</span>
                                <span className="capitalize">{store.backend}</span>
                                <span>•</span>
                                <span>{store.document_count} docs</span>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}

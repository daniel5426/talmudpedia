"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import {
    ChevronLeft,
    Bot,
    Loader2,
    Save
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
    Card,
    CardContent,
    CardDescription,
    CardFooter,
    CardHeader,
    CardTitle,
} from "@/components/ui/card"
import { agentService } from "@/services"

export default function NewAgentPage() {
    const router = useRouter()
    const [isLoading, setIsLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [name, setName] = useState("")
    const [slug, setSlug] = useState("")
    const [description, setDescription] = useState("")

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!name || !slug) return
        setError(null)

        try {
            setIsLoading(true)
            const newAgent = await agentService.createAgent({
                name,
                slug,
                description,
                status: 'draft'
            })
            router.push(`/admin/agents/${newAgent.id}/builder`)
        } catch (err: any) {
            console.error("Failed to create agent:", err)
            setError(err.message || "Failed to create agent. Please try again.")
        } finally {
            setIsLoading(false)
        }
    }

    // Auto-generate slug from name
    const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const val = e.target.value
        setName(val)
        if (!slug || slug === name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')) {
            setSlug(val.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, ''))
        }
    }

    return (
        <div className="p-6 max-w-2xl mx-auto space-y-6 w-full">
            <Button variant="ghost" onClick={() => router.push("/admin/agents")} className="mb-4">
                <ChevronLeft className="mr-2 h-4 w-4" />
                Back to Agents
            </Button>

            <Card>
                <CardHeader>
                    <div className="flex items-center gap-2 mb-2">
                        <div className="bg-primary/10 p-2 rounded-lg">
                            <Bot className="h-6 w-6 text-primary" />
                        </div>
                        <CardTitle className="text-2xl">Create New Agent</CardTitle>
                    </div>
                    <CardDescription>
                        Define the basic identity of your new AI agent. You'll configure the graph logic next.
                    </CardDescription>
                </CardHeader>
                <form onSubmit={handleSubmit}>
                    <CardContent className="space-y-4">
                        <div className="space-y-2">
                            <Label htmlFor="name">Agent Name</Label>
                            <Input
                                id="name"
                                placeholder="e.g. Research Assistant"
                                value={name}
                                onChange={handleNameChange}
                                required
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="slug">Unique Slug</Label>
                            <Input
                                id="slug"
                                placeholder="e.g. research-assistant"
                                value={slug}
                                onChange={(e) => {
                                    setSlug(e.target.value.toLowerCase().replace(/\s+/g, '-'))
                                    setError(null)
                                }}
                                className={error?.includes("slug") ? "border-red-500" : ""}
                                required
                            />
                            {error?.includes("slug") ? (
                                <p className="text-sm font-medium text-red-500">
                                    {error}
                                </p>
                            ) : (
                                <p className="text-[10px] text-muted-foreground">
                                    This is used in API calls and cannot be changed later.
                                </p>
                            )}
                        </div>
                        {error && !error.includes("slug") && (
                            <div className="p-3 rounded-md bg-red-50 border border-red-200 text-sm text-red-600">
                                {error}
                            </div>
                        )}
                        <div className="space-y-2">
                            <Label htmlFor="description">Description (Optional)</Label>
                            <Textarea
                                id="description"
                                placeholder="Describe what this agent does..."
                                value={description}
                                onChange={(e) => setDescription(e.target.value)}
                                rows={4}
                            />
                        </div>
                    </CardContent>
                    <CardFooter className="flex justify-end gap-3 pt-6">
                        <Button variant="outline" type="button" onClick={() => router.push("/admin/agents")}>
                            Cancel
                        </Button>
                        <Button type="submit" disabled={isLoading || !name || !slug}>
                            {isLoading ? (
                                <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    Creating...
                                </>
                            ) : (
                                <>
                                    <Save className="mr-2 h-4 w-4" />
                                    Create & Open Builder
                                </>
                            )}
                        </Button>
                    </CardFooter>
                </form>
            </Card>
        </div>
    )
}

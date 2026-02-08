"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import {
    Plus,
    Search,
    MoreVertical,
    Play,
    Trash2,
    ExternalLink,
    Loader2,
    AlertCircle
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import {
    Card,
    CardContent,
    CardDescription,
    CardFooter,
    CardHeader,
    CardTitle,
} from "@/components/ui/card"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Badge } from "@/components/ui/badge"
import { agentService, Agent } from "@/services"

export default function AgentsPage() {
    const router = useRouter()
    const [agents, setAgents] = useState<Agent[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [searchQuery, setSearchQuery] = useState("")

    useEffect(() => {
        loadAgents()
    }, [])

    const loadAgents = async () => {
        try {
            setIsLoading(true)
            const data = await agentService.listAgents()
            setAgents(data.agents)
            setError(null)
        } catch (err) {
            console.error("Failed to load agents:", err)
            setError("Failed to load agents. Please try again later.")
        } finally {
            setIsLoading(false)
        }
    }

    const filteredAgents = agents.filter(agent =>
        agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        agent.slug?.toLowerCase().includes(searchQuery.toLowerCase())
    )

    const getStatusBadge = (status: Agent['status']) => {
        switch (status) {
            case 'published':
                return <Badge variant="default" className="bg-green-500 hover:bg-green-600">Published</Badge>
            case 'draft':
                return <Badge variant="secondary">Draft</Badge>
            case 'archived':
                return <Badge variant="outline">Archived</Badge>
            default:
                return <Badge variant="outline">{status}</Badge>
        }
    }

    return (
        <div className="flex w-full flex-col h-screen bg-background overflow-hidden">
            <header className="h-12 flex items-center justify-between px-4 bg-background z-30 shrink-0">
                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2">
                        <CustomBreadcrumb items={[
                            { label: "Agents Management", href: "/admin/agents", active: true },
                        ]} />
                    </div>
                </div>

                <div className="flex items-center gap-4">
                    <div className="relative w-64">
                        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                        <Input
                            placeholder="Search agents..."
                            className="pl-8 h-9 bg-muted/50 border-none focus-visible:ring-1"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            disabled={isLoading}
                        />
                    </div>
                    <Button size="sm" className="h-9" onClick={() => router.push("/admin/agents/new")} disabled={isLoading}>
                        <Plus className="mr-2 h-4 w-4" />
                        Create Agent
                    </Button>
                </div>
            </header>

            <main className="flex-1 overflow-y-auto p-6">
                <div className="max-w-7xl mx-auto space-y-6">

                    {isLoading ? (
                        <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4">
                            <Loader2 className="h-8 w-8 animate-spin text-primary" />
                            <p className="text-muted-foreground">Loading agents...</p>
                        </div>
                    ) : error ? (
                        <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4 text-center">
                            <AlertCircle className="h-12 w-12 text-destructive" />
                            <div className="space-y-2">
                                <h3 className="text-lg font-medium">Error</h3>
                                <p className="text-muted-foreground max-w-sm">{error}</p>
                            </div>
                            <Button variant="outline" onClick={loadAgents}>Try Again</Button>
                        </div>
                    ) : filteredAgents.length === 0 ? (
                        <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4 text-center border-2 border-dashed rounded-lg">
                            <div className="bg-muted p-4 rounded-full">
                                <Plus className="h-8 w-8 text-muted-foreground" />
                            </div>
                            <div className="space-y-1">
                                <h3 className="text-lg font-medium">No agents found</h3>
                                <p className="text-muted-foreground max-w-sm">
                                    {searchQuery ? "No agents match your search criteria." : "Get started by creating your first AI agent."}
                                </p>
                            </div>
                            <Button variant="secondary" onClick={() => router.push("/admin/agents/new")}>
                                Create your first agent
                            </Button>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                            {filteredAgents.map((agent) => (
                                <Card key={agent.id} className="flex flex-col relative">
                                    <CardHeader className="space-y-1">
                                        <div className="flex items-start justify-between">
                                            <div className="space-y-1 flex-1 pr-8">
                                                <div className="flex items-center gap-2">
                                                    <CardTitle className="line-clamp-1">{agent.name}</CardTitle>
                                                    {getStatusBadge(agent.status)}
                                                </div>
                                                <CardDescription>v{agent.version} • {agent.slug}</CardDescription>
                                            </div>
                                            <DropdownMenu>
                                                <DropdownMenuTrigger asChild>
                                                    <Button variant="ghost" size="icon" className="absolute top-2 right-2 h-8 w-8">
                                                        <MoreVertical className="h-4 w-4" />
                                                    </Button>
                                                </DropdownMenuTrigger>
                                                <DropdownMenuContent align="end">
                                                    <DropdownMenuItem onClick={() => router.push(`/admin/agents/${agent.id}/builder`)}>
                                                        Edit Builder
                                                    </DropdownMenuItem>
                                                    <DropdownMenuItem>Settings</DropdownMenuItem>
                                                    <DropdownMenuItem className="text-destructive">Delete</DropdownMenuItem>
                                                </DropdownMenuContent>
                                            </DropdownMenu>
                                        </div>
                                    </CardHeader>
                                    <CardContent className="flex-1">
                                        <p className="text-sm text-muted-foreground line-clamp-3">
                                            {agent.description || "No description provided."}
                                        </p>
                                    </CardContent>
                                    <CardFooter className="pt-0 flex justify-between">
                                        <div className="text-xs text-muted-foreground">
                                            Updated {new Date(agent.updated_at).toLocaleDateString()}
                                        </div>
                                        <div className="flex gap-2">
                                            <Button variant="outline" size="sm" onClick={() => router.push(`/admin/agents/${agent.id}/builder`)}>
                                                <ExternalLink className="mr-2 h-3 w-3" />
                                                Open
                                            </Button>
                                            <Button size="sm" onClick={() => router.push(`/admin/agents/playground?agentId=${agent.id}`)}>
                                                <Play className="mr-2 h-3 w-3" />
                                                Run
                                            </Button>
                                        </div>
                                    </CardFooter>
                                </Card>
                            ))}
                        </div>
                    )}
                </div>
            </main>
        </div>
    )
}

"use client"

import { useState, useEffect } from "react"
import { useParams, useRouter } from "next/navigation"
import {
    Play,
    ChevronLeft,
    Loader2,
    AlertCircle,
    Send,
    Bot,
    User,
    Terminal
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from "@/components/ui/card"
import { agentService, Agent } from "@/services/agent-resources"

export default function AgentRunPage() {
    const { id } = useParams()
    const router = useRouter()
    const [agent, setAgent] = useState<Agent | null>(null)
    const [isLoading, setIsLoading] = useState(true)
    const [isExecuting, setIsExecuting] = useState(false)
    const [inputValue, setInputValue] = useState("")
    const [output, setOutput] = useState<any>(null)
    const [logs, setLogs] = useState<string[]>([])

    useEffect(() => {
        if (id) {
            loadAgent()
        }
    }, [id])

    const loadAgent = async () => {
        try {
            setIsLoading(true)
            const data = await agentService.getAgent(id as string)
            setAgent(data)
        } catch (err) {
            console.error("Failed to load agent:", err)
        } finally {
            setIsLoading(false)
        }
    }

    const handleRun = async () => {
        if (!inputValue || !agent) return

        try {
            setIsExecuting(true)
            setLogs(prev => [...prev, `Starting execution with input: "${inputValue}"...`])

            const result = await agentService.executeAgent(agent.id, { text: inputValue })

            setOutput(result)
            setLogs(prev => [...prev, "Execution completed successfully."])
        } catch (err) {
            console.error("Execution failed:", err)
            setLogs(prev => [...prev, `Error: ${err instanceof Error ? err.message : String(err)}`])
        } finally {
            setIsExecuting(false)
        }
    }

    if (isLoading) {
        return (
            <div className="flex w-full flex-col items-center justify-center min-h-screen space-y-4">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                <p className="text-muted-foreground">Loading agent runner...</p>
            </div>
        )
    }

    if (!agent) {
        return (
            <div className="flex w-full flex-col items-center justify-center min-h-screen space-y-4 text-center p-6">
                <AlertCircle className="h-12 w-12 text-destructive" />
                <h3 className="text-lg font-medium">Agent Not Found</h3>
                <Button variant="outline" onClick={() => router.push("/admin/agents")}>
                    Back to Agents
                </Button>
            </div>
        )
    }

    return (
        <div className="p-6 w-full max-w-5xl mx-auto space-y-6 flex flex-col h-[calc(100vh-2rem)]">
            <header className="flex items-center justify-between border-b pb-4 shrink-0">
                <div className="flex items-center gap-4">
                    <Button variant="ghost" size="icon" onClick={() => router.push("/admin/agents")}>
                        <ChevronLeft className="h-4 w-4" />
                    </Button>
                    <div>
                        <h1 className="text-2xl font-bold flex items-center gap-2">
                            Run Agent: {agent.name}
                        </h1>
                        <p className="text-sm text-muted-foreground">Testing playground for agent workflows</p>
                    </div>
                </div>
                <Button variant="outline" size="sm" onClick={() => router.push(`/admin/agents/${agent.id}/builder`)}>
                    Open Builder
                </Button>
            </header>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 flex-1 min-h-0">
                {/* Input Panel */}
                <div className="flex flex-col space-y-4 h-full">
                    <Card className="flex flex-col h-full">
                        <CardHeader>
                            <CardTitle className="text-lg flex items-center gap-2">
                                <User className="h-4 w-4" />
                                Input Parameters
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="flex-1 space-y-4">
                            <div className="space-y-2">
                                <label className="text-sm font-medium">Text Prompt</label>
                                <textarea
                                    className="w-full h-40 p-3 rounded-md border bg-background resize-none focus:outline-none focus:ring-2 focus:ring-primary"
                                    placeholder="Enter input for the agent..."
                                    value={inputValue}
                                    onChange={(e) => setInputValue(e.target.value)}
                                />
                            </div>
                        </CardContent>
                        <CardFooter className="border-t pt-4">
                            <Button
                                className="w-full"
                                onClick={handleRun}
                                disabled={isExecuting || !inputValue}
                            >
                                {isExecuting ? (
                                    <>
                                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                        Running Agent...
                                    </>
                                ) : (
                                    <>
                                        <Send className="mr-2 h-4 w-4" />
                                        Execute Agent
                                    </>
                                )}
                            </Button>
                        </CardFooter>
                    </Card>
                </div>

                {/* Output Panel */}
                <div className="flex flex-col space-y-4 h-full">
                    <Card className="flex flex-col h-full">
                        <CardHeader>
                            <CardTitle className="text-lg flex items-center gap-2">
                                <Bot className="h-4 w-4" />
                                Execution Result
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="flex-1 overflow-auto bg-muted/20 p-4 font-mono text-sm">
                            {output ? (
                                <pre className="whitespace-pre-wrap">{JSON.stringify(output, null, 2)}</pre>
                            ) : (
                                <div className="h-full flex items-center justify-center text-muted-foreground italic">
                                    Agent output will appear here after execution
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    <Card className="h-1/3 min-h-[150px]">
                        <CardHeader className="py-2 px-4 border-b">
                            <CardTitle className="text-xs flex items-center gap-2 uppercase tracking-wider text-muted-foreground">
                                <Terminal className="h-3 w-3" />
                                Trace Logs
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="p-3 overflow-auto h-[calc(100%-40px)]">
                            <div className="space-y-1">
                                {logs.map((log, i) => (
                                    <div key={i} className="text-[11px] font-mono border-l-2 border-primary/20 pl-2 py-0.5">
                                        <span className="text-muted-foreground">[{new Date().toLocaleTimeString()}]</span> {log}
                                    </div>
                                ))}
                                {logs.length === 0 && (
                                    <div className="text-[11px] text-muted-foreground italic">No logs generated yet.</div>
                                )}
                            </div>
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>
    )
}

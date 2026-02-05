
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import { X } from "lucide-react"
import { Separator } from "@/components/ui/separator"

interface ExecutionDetailsSkeletonProps {
    onClose: () => void
}

export function ExecutionDetailsSkeleton({ onClose }: ExecutionDetailsSkeletonProps) {
    return (
        <div className="flex flex-col h-full bg-background w-full">
            <div className="flex items-center justify-between p-4 border-b">
                <div className="flex items-center gap-2">
                    <Skeleton className="h-6 w-32" /> {/* Title */}
                    <Skeleton className="h-5 w-20" /> {/* Badge */}
                </div>
                <Button variant="ghost" size="icon" onClick={onClose}>
                    <X className="h-4 w-4" />
                </Button>
            </div>

            <div className="flex-1 p-4 space-y-6">
                <div className="space-y-6">
                    <div className="space-y-2">
                        <Skeleton className="h-4 w-16" /> {/* Section Title */}
                        <div className="grid grid-cols-2 gap-2 text-sm">
                            <Skeleton className="h-3 w-12" /> <Skeleton className="h-3 w-24" />
                            <Skeleton className="h-3 w-16" /> <Skeleton className="h-3 w-20" />
                            <Skeleton className="h-3 w-14" /> <Skeleton className="h-3 w-16" />
                            <Skeleton className="h-3 w-14" /> <Skeleton className="h-3 w-10" />
                        </div>
                    </div>

                    <Separator />

                    <div className="space-y-2">
                        <Skeleton className="h-4 w-20" />
                        <Skeleton className="h-[100px] w-full" />
                    </div>

                    <div className="space-y-2">
                        <Skeleton className="h-4 w-20" />
                        <Skeleton className="h-[100px] w-full" />
                    </div>
                </div>
            </div>
        </div>
    )
}

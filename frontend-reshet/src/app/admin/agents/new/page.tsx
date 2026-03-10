import { redirect } from "next/navigation"

export default function NewAgentPage() {
    redirect("/admin/agents?create=1")
}

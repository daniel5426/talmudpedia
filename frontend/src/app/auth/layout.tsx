export default function AuthLayout({ children }: { children: React.ReactNode }) {
    return (
        <div style={{ backgroundImage: "url(/auth-banner.jpeg)", backgroundSize: "cover", backgroundPosition: "center" }} className="flex min-h-svh flex-col items-center justify-center p-6 md:p-10">
            <div className="w-full max-w-sm md:max-w-4xl">
                {children}
            </div>
        </div>
    )
}
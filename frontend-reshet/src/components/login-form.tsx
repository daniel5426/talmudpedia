"use client"
import { cn } from "@/lib/utils"
import { motion } from "framer-motion"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldSeparator,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { useState } from "react"
import { useRouter } from "next/navigation"
import { authService } from "@/services"
import { useAuthStore } from "@/lib/store/useAuthStore"
import { GoogleLogin } from "@react-oauth/google"

export function LoginForm({
  className,
  ...props
}: React.ComponentProps<"div">) {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const router = useRouter()
  const setAuth = useAuthStore((state) => state.setAuth)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)

    try {
      const { access_token } = await authService.login(email, password)
      // Set token first to allow getMe to work
      useAuthStore.getState().setAuth(null as any, access_token)
      
      const user = await authService.getProfile()
      setAuth(user, access_token)
      router.push("/chat")
    } catch (err: any) {
      setError(err.message || "Login failed")
      // Clear token if login failed
      useAuthStore.getState().logout()
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleSuccess = async (credentialResponse: any) => {
    if (!credentialResponse.credential) return;
    
    setLoading(true);
    setError("");
    try {
      const { access_token } = await authService.googleLogin(credentialResponse.credential);
      useAuthStore.getState().setAuth(null as any, access_token);
      const user = await authService.getProfile();
      setAuth(user, access_token);
      router.push("/chat");
    } catch (err: any) {
      setError(err.message || "Google login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
    >
      <div className={cn("", className)}  {...props}>
      <Card className="overflow-hidden p-0 max-w-md mx-auto">
        <CardContent className=" p-0 ">
          <form className="p-6 md:p-8 pb-4" onSubmit={handleSubmit}>
            <FieldGroup>
              <div className="flex flex-col items-center gap-2 text-center">
                <h1 className="text-2xl font-bold">ברוך הבא</h1>
                <p className="text-muted-foreground text-balance">
                  התחברות לחשבון רשת
                </p>
              </div>
              {error && (
                <div className="text-red-500 text-sm text-center">{error}</div>
              )}
              <Field>
                <FieldLabel htmlFor="email">אימייל</FieldLabel>
                <Input
                  id="email"
                  type="email"
                  placeholder="name@example.com"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </Field>
              <Field>
                <div className="flex items-center">
                  <FieldLabel htmlFor="password">סיסמה</FieldLabel>
                  <a
                    href="#"
                    className="mr-auto text-sm underline-offset-2 hover:underline"
                  >
                    שכחת סיסמה?
                  </a>
                </div>
                <Input 
                  id="password" 
                  type="password" 
                  required 
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </Field>
              <Field>
                <Button type="submit" disabled={loading}>
                  {loading ? "מתחבר..." : "התחבר"}
                </Button>
              </Field>
              <FieldSeparator className="*:data-[slot=field-separator-content]:bg-card">
                או המשך עם
              </FieldSeparator>
              <Field className="flex justify-center">
                <GoogleLogin
                  onSuccess={handleGoogleSuccess}
                  onError={() => setError("Google Login Failed")}
                  useOneTap
                  theme="outline"
                  size="large"
                  text="signin_with"
                  shape="rectangular"
                  width="360"
                />
              </Field>
              <FieldDescription className="text-center">
                אין לך חשבון? <a href="/auth/signup">הרשמה</a>
              </FieldDescription>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
      <FieldDescription className="p-6 text-center text-white">
        בלחיצה על המשך, הינך מסכים ל<a href="#">תנאי השימוש</a> ול<a href="#">מדיניות הפרטיות</a> שלנו.
      </FieldDescription>
      </div>
    </motion.div>
  )
}

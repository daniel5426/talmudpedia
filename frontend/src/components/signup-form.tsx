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

export function SignupForm({
  className,
  ...props
}: React.ComponentProps<"div">) {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [fullName, setFullName] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const router = useRouter()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)

    try {
      await authService.register(email, password, fullName)
      // Auto login after registration
      const { access_token } = await authService.login(email, password)
      useAuthStore.getState().setAuth(null as any, access_token)
      const user = await authService.getProfile()
      useAuthStore.getState().setAuth(user, access_token)
      router.push("/chat")
    } catch (err: any) {
      setError(err.message || "Registration failed")
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
      useAuthStore.getState().setAuth(user, access_token);
      router.push("/chat");
    } catch (err: any) {
      setError(err.message || "Google signup failed");
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
      <div className={cn("", className)} {...props}>
      <Card className="overflow-hidden p-0 max-w-md mx-auto">
        <CardContent className=" p-0 ">
          <form className="p-6 md:p-8 pb-4" onSubmit={handleSubmit}>
            <FieldGroup>
              <div className="flex flex-col items-center gap-2 text-center">
                <h1 className="text-2xl font-bold">יצירת חשבון</h1>
                <p className="text-muted-foreground text-balance">
                  התחברות ל-Talmudpedia
                </p>
              </div>
              {error && (
                <div className="text-red-500 text-sm text-center">{error}</div>
              )}
              <Field>
                <FieldLabel htmlFor="name">שם מלא</FieldLabel>
                <Input
                  id="name"
                  type="text"
                  placeholder="ישראל ישראלי"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="email">אימייל</FieldLabel>
                <Input
                  id="email"
                  type="email"
                  placeholder="m@example.com"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="password">סיסמה</FieldLabel>
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
                  {loading ? "יוצר חשבון..." : "הרשמה"}
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
                  text="signup_with"
                  shape="rectangular"
                  width="360"
                />
              </Field>
              <FieldDescription className="text-center">
                כבר יש לך חשבון? <a href="/auth/login">התחברות</a>
              </FieldDescription>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
      <FieldDescription className="px-6 text-center text-white">
        בלחיצה על המשך, הינך מסכים ל<a href="#">תנאי השימוש</a> ול<a href="#">מדיניות הפרטיות</a> שלנו.
      </FieldDescription>
      </div>
    </motion.div>
  )
}

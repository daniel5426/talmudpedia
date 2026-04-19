import { redirect } from "next/navigation";

const AUTH_NAV_BASE_URL = String(process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8026").trim().replace(/\/$/, "");

function buildReturnTo(target?: string) {
  const fallback = "/admin/agents/playground";
  const resolved = target || fallback;

  if (/^https?:\/\//i.test(resolved)) {
    return resolved;
  }

  const origin = process.env.NEXT_PUBLIC_APP_URL || "";
  if (!origin) {
    return resolved;
  }

  return `${origin}${resolved.startsWith("/") ? resolved : `/${resolved}`}`;
}

export default async function SignupPage({
  searchParams,
}: {
  searchParams: Promise<{ return_to?: string }>;
}) {
  const params = await searchParams;
  const returnTo = buildReturnTo(params.return_to);

  redirect(`${AUTH_NAV_BASE_URL}/auth/signup?return_to=${encodeURIComponent(returnTo)}`);
}

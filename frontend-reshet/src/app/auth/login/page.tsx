import { redirect } from "next/navigation";

const AUTH_NAV_BASE_URL = "/api/py";

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

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ return_to?: string }>;
}) {
  const params = await searchParams;
  const returnTo = buildReturnTo(params.return_to);

  redirect(`${AUTH_NAV_BASE_URL}/auth/login?return_to=${encodeURIComponent(returnTo)}`);
}

import Link from "next/link";

type LegalLinksProps = {
  prefix: string;
};

export function LegalLinks({ prefix }: LegalLinksProps) {
  return (
    <p className="text-xs text-gray-400">
      {prefix}{" "}
      <Link href="/terms" className="text-[#7c5aed] hover:underline">
        Terms of Service
      </Link>{" "}
      and{" "}
      <Link href="/privacy" className="text-[#7c5aed] hover:underline">
        Privacy Policy
      </Link>
    </p>
  );
}

"use client";

import { cn } from "@/lib/utils";
import { useState } from "react";

type ContactFormProps = {
  source: string;
  className?: string;
  compact?: boolean;
  submitLabel?: string;
  successMessage?: string;
};

type FormState = {
  name: string;
  email: string;
  company: string;
  message: string;
  website: string;
};

const INITIAL_FORM_STATE: FormState = {
  name: "",
  email: "",
  company: "",
  message: "",
  website: "",
};

export function ContactForm({
  source,
  className,
  compact = false,
  submitLabel = "Send request",
  successMessage = "Message sent. I’ll get it in email and can follow up from there.",
}: ContactFormProps) {
  const [form, setForm] = useState<FormState>(INITIAL_FORM_STATE);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const handleChange = (field: keyof FormState, value: string) => {
    setForm((current) => ({
      ...current,
      [field]: value,
    }));
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setSuccess("");

    try {
      const response = await fetch("/api/contact", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          ...form,
          source,
        }),
      });

      const payload = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(
          typeof payload?.message === "string" ? payload.message : "Unable to send message.",
        );
      }

      setForm(INITIAL_FORM_STATE);
      setSuccess(successMessage);
    } catch (submitError) {
      setError(
        submitError instanceof Error && submitError.message
          ? submitError.message
          : "Unable to send message.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className={cn(
        "bg-white",
        compact ? "" : "p-2",
        className,
      )}
    >
      <div className={cn("grid", compact ? "gap-4 md:grid-cols-2" : "gap-8 md:grid-cols-2")}>
        <div className="space-y-2">
          <label className="text-[11px] font-medium text-gray-400 uppercase tracking-widest block">Name</label>
          <input
            type="text"
            value={form.name}
            onChange={(event) => handleChange("name", event.target.value)}
            placeholder="John Doe"
            className="w-full bg-transparent border-t-0 border-l-0 border-r-0 border-b border-gray-200 px-0 py-2.5 text-sm text-gray-900 placeholder:text-gray-300 outline-none focus:ring-0 focus:border-black transition-colors shadow-none"
            style={{ boxShadow: 'none' }}
            required
          />
        </div>

        <div className="space-y-2">
          <label className="text-[11px] font-medium text-gray-400 uppercase tracking-widest block">Email</label>
          <input
            type="email"
            value={form.email}
            onChange={(event) => handleChange("email", event.target.value)}
            placeholder="name@example.com"
            className="w-full bg-transparent border-t-0 border-l-0 border-r-0 border-b border-gray-200 px-0 py-2.5 text-sm text-gray-900 placeholder:text-gray-300 outline-none focus:ring-0 focus:border-black transition-colors shadow-none"
            style={{ boxShadow: 'none' }}
            required
          />
        </div>

        <div className="space-y-2 md:col-span-2">
          <label className="text-[11px] font-medium text-gray-400 uppercase tracking-widest block">
            Company or use case
          </label>
          <input
            type="text"
            value={form.company}
            onChange={(event) => handleChange("company", event.target.value)}
            placeholder="What are you building?"
            className="w-full bg-transparent border-t-0 border-l-0 border-r-0 border-b border-gray-200 px-0 py-2.5 text-sm text-gray-900 placeholder:text-gray-300 outline-none focus:ring-0 focus:border-black transition-colors shadow-none"
            style={{ boxShadow: 'none' }}
          />
        </div>

        <div className="space-y-2 md:col-span-2">
          <label className="text-[11px] font-medium text-gray-400 uppercase tracking-widest block">Message</label>
          <textarea
            value={form.message}
            onChange={(event) => handleChange("message", event.target.value)}
            placeholder="Tell us what you need..."
            className={cn(
              "w-full resize-y bg-transparent border-t-0 border-l-0 border-r-0 border-b border-gray-200 px-0 py-3 text-sm leading-relaxed text-gray-900 placeholder:text-gray-300 outline-none focus:ring-0 focus:border-black transition-colors shadow-none",
              compact ? "min-h-[70px]" : "min-h-[120px]"
            )}
            style={{ boxShadow: 'none' }}
            required
          />
        </div>
      </div>

      <label className="sr-only" aria-hidden="true">
        Website
        <input
          tabIndex={-1}
          autoComplete="off"
          value={form.website}
          onChange={(event) => handleChange("website", event.target.value)}
          name="website"
        />
      </label>

      {error ? (
        <div className="mt-6 rounded-xl border border-red-100 bg-red-50/50 px-4 py-3 text-sm text-red-600">
          {error}
        </div>
      ) : null}

      {success ? (
        <div className="mt-6 rounded-xl border border-emerald-100 bg-emerald-50/50 px-4 py-3 text-sm text-emerald-700">
          {success}
        </div>
      ) : null}

      <div className={cn(compact ? "mt-6" : "mt-10", "flex flex-col sm:flex-row sm:items-center gap-6", compact ? "justify-end" : "justify-between")}>
        {!compact && (
          <p className="text-xs text-gray-400 font-mono tracking-wide">
            Response usually within 24 hours
          </p>
        )}
        <button
          type="submit"
          disabled={submitting}
          className={cn(
            "inline-flex items-center justify-center rounded-xl bg-black px-8 py-3 text-sm font-medium text-white transition-all hover:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-black focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
            compact ? "w-full" : ""
          )}
        >
          {submitting ? "Sending..." : submitLabel}
        </button>
      </div>
    </form>
  );
}

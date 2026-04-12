import { NextResponse } from "next/server";

const DEFAULT_CONTACT_EMAIL = "danielbenassaya2626@gmail.com";
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type ContactRequestBody = {
  name?: unknown;
  email?: unknown;
  company?: unknown;
  message?: unknown;
  source?: unknown;
  website?: unknown;
};

function toTrimmedString(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function escapeHtml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export async function POST(request: Request) {
  let body: ContactRequestBody;

  try {
    body = (await request.json()) as ContactRequestBody;
  } catch {
    return NextResponse.json({ message: "Invalid request body." }, { status: 400 });
  }

  const name = toTrimmedString(body.name);
  const email = toTrimmedString(body.email);
  const company = toTrimmedString(body.company);
  const message = toTrimmedString(body.message);
  const source = toTrimmedString(body.source) || "unknown";
  const website = toTrimmedString(body.website);

  if (website) {
    return NextResponse.json({ ok: true });
  }

  if (!name || !email || !message) {
    return NextResponse.json(
      { message: "Name, email, and message are required." },
      { status: 400 },
    );
  }

  if (!EMAIL_REGEX.test(email)) {
    return NextResponse.json({ message: "Enter a valid email address." }, { status: 400 });
  }

  if (message.length < 10) {
    return NextResponse.json(
      { message: "Message is too short. Add a little more detail." },
      { status: 400 },
    );
  }

  const resendApiKey = process.env.RESEND_API_KEY;
  const fromEmail = process.env.CONTACT_FROM_EMAIL;
  const toEmail = process.env.CONTACT_EMAIL_TO || DEFAULT_CONTACT_EMAIL;

  if (!resendApiKey || !fromEmail) {
    return NextResponse.json(
      { message: "Contact form email delivery is not configured yet." },
      { status: 503 },
    );
  }

  const safeName = escapeHtml(name);
  const safeEmail = escapeHtml(email);
  const safeCompany = escapeHtml(company || "Not provided");
  const safeMessage = escapeHtml(message).replaceAll("\n", "<br />");
  const safeSource = escapeHtml(source);

  const resendResponse = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${resendApiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: fromEmail,
      to: [toEmail],
      subject: `[AGENTS24] Contact request from ${name}`,
      html: `
        <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #111827;">
          <h2 style="margin-bottom: 16px;">New AGENTS24 contact request</h2>
          <p><strong>Name:</strong> ${safeName}</p>
          <p><strong>Email:</strong> ${safeEmail}</p>
          <p><strong>Company / use case:</strong> ${safeCompany}</p>
          <p><strong>Source:</strong> ${safeSource}</p>
          <p><strong>Message:</strong></p>
          <div>${safeMessage}</div>
        </div>
      `,
      text: [
        "New AGENTS24 contact request",
        `Name: ${name}`,
        `Email: ${email}`,
        `Company / use case: ${company || "Not provided"}`,
        `Source: ${source}`,
        "",
        "Message:",
        message,
      ].join("\n"),
    }),
  });

  if (!resendResponse.ok) {
    const resendError = await resendResponse.text().catch(() => "Unable to read provider error.");
    console.error("Contact form delivery failed:", resendError);
    return NextResponse.json(
      { message: "Unable to send the message right now." },
      { status: 502 },
    );
  }

  return NextResponse.json({ ok: true });
}

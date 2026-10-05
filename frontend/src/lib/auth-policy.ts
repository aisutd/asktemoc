/**
 * Who may sign in. Mirrors the API's check in backend/app/core/auth.py.
 *
 * - The email must end with "@" + ALLOWED_EMAIL_DOMAIN (default utdallas.edu),
 *   compared case-insensitively.
 * - ALLOWED_EMAILS (comma-separated) admits extra addresses, but only when the
 *   app runs in development (`next dev`), for teammates testing with other
 *   accounts. The API must also run with ENVIRONMENT=development and the same
 *   ALLOWED_EMAILS for those accounts to get answers.
 */

export function allowedEmailDomain(): string {
  return (process.env.ALLOWED_EMAIL_DOMAIN || "utdallas.edu")
    .trim()
    .toLowerCase()
    .replace(/^@/, "");
}

function devAllowedEmails(): string[] {
  if (process.env.NODE_ENV !== "development") return [];
  return (process.env.ALLOWED_EMAILS || "")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
}

export function isAllowedEmail(email: string | null | undefined): boolean {
  if (!email) return false;
  const normalized = email.trim().toLowerCase();
  if (normalized.endsWith(`@${allowedEmailDomain()}`)) return true;
  return devAllowedEmails().includes(normalized);
}

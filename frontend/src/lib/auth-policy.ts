/**
 * Who may sign in. Mirrors backend/app/core/auth.py.
 * Email must end with "@" + ALLOWED_EMAIL_DOMAIN (default utdallas.edu).
 */

export function allowedEmailDomain(): string {
  return (process.env.ALLOWED_EMAIL_DOMAIN || "utdallas.edu")
    .trim()
    .toLowerCase()
    .replace(/^@/, "");
}

export function isAllowedEmail(email: string | null | undefined): boolean {
  if (!email) return false;
  return email.trim().toLowerCase().endsWith(`@${allowedEmailDomain()}`);
}

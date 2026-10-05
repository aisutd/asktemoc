import NextAuth from "next-auth";
import type { Provider } from "next-auth/providers";
import Google from "next-auth/providers/google";
import MicrosoftEntraID from "next-auth/providers/microsoft-entra-id";
import { isAllowedEmail } from "@/lib/auth-policy";

/**
 * Providers are enabled by their env vars (see .env.example):
 * - Microsoft Entra ID (UTD Microsoft 365, the production path):
 *   AUTH_MICROSOFT_ENTRA_ID_ID / _SECRET / _ISSUER
 * - Google (handy in development): AUTH_GOOGLE_ID / _SECRET
 */
const providers: Provider[] = [];
/** Enabled providers, for rendering the sign-in page. */
export const providerList: { id: string; name: string }[] = [];
if (
  process.env.AUTH_MICROSOFT_ENTRA_ID_ID &&
  process.env.AUTH_MICROSOFT_ENTRA_ID_SECRET &&
  process.env.AUTH_MICROSOFT_ENTRA_ID_ISSUER
) {
  providers.push(MicrosoftEntraID);
  providerList.push({ id: "microsoft-entra-id", name: "UT Dallas (Microsoft)" });
}
if (process.env.AUTH_GOOGLE_ID && process.env.AUTH_GOOGLE_SECRET) {
  providers.push(Google);
  providerList.push({ id: "google", name: "Google" });
}

/** Tenant segment of the configured Entra issuer, e.g. the UTD tenant GUID. */
function entraTenant(): string | undefined {
  return process.env.AUTH_MICROSOFT_ENTRA_ID_ISSUER?.match(
    /microsoftonline\.com\/([^/]+)\/v2\.0/,
  )?.[1];
}

const MULTI_TENANT = new Set(["common", "organizations", "consumers"]);

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers,
  session: { strategy: "jwt" },
  pages: { signIn: "/signin", error: "/signin" },
  callbacks: {
    signIn({ account, profile, user }) {
      const email = profile?.email ?? user.email;
      // Reject explicitly unverified emails (Google sends email_verified).
      if (profile && "email_verified" in profile && profile.email_verified !== true) {
        return false;
      }
      if (account?.provider === "microsoft-entra-id") {
        // Entra does not verify the email claim across tenants, so only trust a
        // single-tenant issuer and require the token to come from that tenant.
        const tenant = entraTenant();
        if (!tenant || MULTI_TENANT.has(tenant) || profile?.tid !== tenant) {
          console.warn("[auth] rejected Entra sign-in: issuer/tenant mismatch");
          return false;
        }
      }
      return isAllowedEmail(email);
    },
    jwt({ token, account }) {
      // Stable per provider account; becomes the API's users.provider_sub.
      if (account) token.sub = `${account.provider}:${account.providerAccountId}`;
      return token;
    },
    session({ session, token }) {
      if (token.sub) session.user.id = token.sub;
      return session;
    },
    authorized({ auth, request }) {
      // Used by middleware. API routes answer 401 themselves rather than redirect.
      const { pathname } = request.nextUrl;
      if (pathname === "/chat" || pathname.startsWith("/chat/")) return !!auth?.user;
      return true;
    },
  },
});

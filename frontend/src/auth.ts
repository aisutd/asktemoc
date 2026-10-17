import NextAuth from "next-auth";
import type { Provider } from "next-auth/providers";
import Google from "next-auth/providers/google";
import MicrosoftEntraID from "next-auth/providers/microsoft-entra-id";
import { isAllowedEmail } from "@/lib/auth-policy";
import { claimsFromProfile, graphUser } from "@/lib/entra";

/**
 * Providers turn on when their env vars are set (see .env.example):
 * - Microsoft Entra ID (UTD Microsoft 365): AUTH_MICROSOFT_ENTRA_ID_ID / _SECRET / _ISSUER
 * - Google (dev): AUTH_GOOGLE_ID / _SECRET
 */
const providers: Provider[] = [];
/** Enabled providers, for rendering the sign-in page. */
export const providerList: { id: string; name: string }[] = [];

if (
  process.env.AUTH_MICROSOFT_ENTRA_ID_ID &&
  process.env.AUTH_MICROSOFT_ENTRA_ID_SECRET &&
  process.env.AUTH_MICROSOFT_ENTRA_ID_ISSUER
) {
  providers.push(
    MicrosoftEntraID({
      clientId: process.env.AUTH_MICROSOFT_ENTRA_ID_ID,
      clientSecret: process.env.AUTH_MICROSOFT_ENTRA_ID_SECRET,
      issuer: process.env.AUTH_MICROSOFT_ENTRA_ID_ISSUER,
      // prompt:login skips login_hint, so the user is not automatically logged in to 
      // currently signed-in account.
      authorization: { params: { prompt: "login" } },
    }),
  );
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

function microsoftEmail(profile: unknown): string | undefined {
  if (!profile || typeof profile !== "object") return undefined;
  const claims = profile as Record<string, unknown>;
  for (const key of ["email", "preferred_username", "upn"]) {
    const value = claims[key];
    if (typeof value === "string" && value.includes("@")) return value;
  }
  return undefined;
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers,
  session: { strategy: "jwt" },
  trustHost: true,
  pages: { signIn: "/signin", error: "/signin" },
  callbacks: {
    signIn({ account, profile, user }) {
      const email = microsoftEmail(profile) ?? user.email;
      if (profile && "email_verified" in profile && profile.email_verified === false) {
        return false;
      }
      // A specific tenant issuer (UTD's GUID) must match the token's tid.
      // common / organizations / consumers skip that check; the email suffix is the gate.
      if (account?.provider === "microsoft-entra-id") {
        const tenant = entraTenant();
        if (tenant && !MULTI_TENANT.has(tenant)) {
          const tid =
            profile && "tid" in profile && typeof profile.tid === "string"
              ? profile.tid
              : undefined;
          if (tid !== tenant) {
            console.warn("[auth] rejected Entra sign-in: issuer/tenant mismatch");
            return false;
          }
        }
      }
      return isAllowedEmail(email);
    },
    async jwt({ token, account, profile }) {
      if (account) {
        token.sub = `${account.provider}:${account.providerAccountId}`;
        if (account.provider === "microsoft-entra-id" && account.access_token) {
          token.entra = claimsFromProfile(profile);
          const graph = await graphUser(account.access_token);
          token.graph = graph.user;
          token.graphError = graph.error;
        }
      }
      return token;
    },
    session({ session, token }) {
      if (token.sub) session.user.id = token.sub;
      session.entra = token.entra;
      session.graph = token.graph;
      session.graphError = token.graphError;
      return session;
    },
    authorized({ auth, request }) {
      const { pathname } = request.nextUrl;
      if (
        pathname === "/chat" ||
        pathname.startsWith("/chat/") ||
        pathname === "/profile"
      ) {
        return !!auth?.user;
      }
      return true;
    },
  },
});

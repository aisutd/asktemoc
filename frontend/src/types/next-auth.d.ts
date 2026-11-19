import type { DefaultSession } from "next-auth";
import type { EntraIdClaims, GraphUser } from "@/lib/entra";

declare module "next-auth" {
  interface Session {
    user: {
      /** users.id from the Auth.js adapter, a text UUID. */
      id: string;
    } & DefaultSession["user"];
    entra?: EntraIdClaims;
    graph?: GraphUser;
    graphError?: string;
  }
}

declare module "@auth/core/jwt" {
  interface JWT {
    entra?: EntraIdClaims;
    graph?: GraphUser;
    graphError?: string;
  }
}
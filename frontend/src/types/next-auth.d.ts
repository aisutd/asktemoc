import type { DefaultSession } from "next-auth";
import type { EntraIdClaims, GraphUser } from "@/lib/entra";

declare module "next-auth" {
  interface Session {
    user: {
      /** "<provider>:<provider account id>", stable per account. */
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
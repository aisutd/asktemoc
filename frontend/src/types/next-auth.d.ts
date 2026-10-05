import type { DefaultSession } from "next-auth";

declare module "next-auth" {
  interface Session {
    user: {
      /** "<provider>:<provider account id>", stable per account. */
      id: string;
    } & DefaultSession["user"];
  }
}

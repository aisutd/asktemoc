import * as React from "react";
import Link from "next/link";
import Image from "next/image";

import { NavigationMenu } from "@/components/ui/navigation-menu";
import { Button } from "@/components/ui/button";
import { auth, signOut } from "@/auth";

export default async function Navbar() {
  const session = await auth();
  const user = session?.user;

  return (
    <NavigationMenu
      viewport={false}
      className="p-4 w-full max-w-none justify-start"
    >
      <Image src="/temochead.svg" alt="logo" width={50} height={50} />
      <h1 className="text-xl font-bold text-utd-primary">Ask Temoc</h1>
      <Link
        href="/"
        className="group inline-flex h-9 w-max items-center justify-center rounded-md bg-background px-4 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground focus-visible:ring-ring/50 outline-none transition-[color,box-shadow] focus-visible:ring-[3px] focus-visible:outline-1 m-4"
      >
        Home
      </Link>
      <div className="ml-auto flex items-center gap-3">
        {user ? (
          <>
            <Link
              href="/profile"
              className="text-sm font-medium text-utd-primary hover:underline"
            >
              {user.name ?? user.email ?? "Profile"}
            </Link>
            <form
              action={async () => {
                "use server";
                await signOut({ redirectTo: "/" });
              }}
            >
              <Button type="submit" variant="outline" size="sm">
                Sign out
              </Button>
            </form>
          </>
        ) : (
          <Button asChild size="sm" className="bg-utd-secondary hover:bg-utd-primary/80 text-white">
            <Link href="/signin">Sign in</Link>
          </Button>
        )}
      </div>
    </NavigationMenu>
  );
}

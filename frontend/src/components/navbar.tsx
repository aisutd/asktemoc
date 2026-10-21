import Link from "next/link";
import Image from "next/image";

import { Button } from "@/components/ui/button";
import { auth, signOut } from "@/auth";

export default async function Navbar() {
  const session = await auth();
  const user = session?.user;

  return (
    <header className="flex w-full shrink-0 items-center gap-4 border-b border-utd-primary/20 px-4 py-3">
      <Link href="/" className="flex items-center gap-3">
        <Image src="/temochead.svg" alt="logo" width={40} height={40} />
        <span className="text-xl font-bold text-utd-primary">Ask Temoc</span>
      </Link>
      <nav className="flex items-center">
        <Link
          href="/"
          className="rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground"
        >
          Home
        </Link>
      </nav>
      <div className="ml-auto flex items-center gap-2">
        {user ? (
          <>
            <Button asChild variant="ghost" size="sm">
              <Link href="/profile">Profile</Link>
            </Button>
            <form
              action={async () => {
                "use server";
                await signOut({ redirectTo: "/" });
              }}
            >
              <Button type="submit" variant="ghost" size="sm">
                Sign out
              </Button>
            </form>
          </>
        ) : (
          <Button asChild size="sm" className="bg-utd-secondary text-white hover:bg-utd-primary/80">
            <Link href="/signin">Sign in</Link>
          </Button>
        )}
      </div>
    </header>
  );
}

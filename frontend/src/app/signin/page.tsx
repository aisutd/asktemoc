import { redirect } from "next/navigation";
import Background from "@/components/ui/background";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { auth, providerList, signIn } from "@/auth";
import { allowedEmailDomain } from "@/lib/auth-policy";

/**
 * Reduce the callback to a same-site path so the sign-in page can't be used as
 * an open redirect. Middleware passes absolute URLs; keep only path + query.
 */
function safeCallback(raw: string | string[] | undefined): string {
  const v = Array.isArray(raw) ? raw[0] : raw;
  if (!v) return "/chat";
  try {
    const url = new URL(v, "http://placeholder.invalid");
    const path = url.pathname + url.search;
    return path.startsWith("/") && !path.startsWith("//") ? path : "/chat";
  } catch {
    return "/chat";
  }
}

function errorMessage(error: string | string[] | undefined): string | null {
  if (!error) return null;
  if (error === "AccessDenied") {
    return `Only verified @${allowedEmailDomain()} accounts can use Ask Temoc.`;
  }
  return "Sign-in failed. Please try again.";
}

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const callbackUrl = safeCallback(params.callbackUrl);
  if ((await auth())?.user) redirect(callbackUrl);
  const error = errorMessage(params.error);

  return (
    <div className="relative min-h-screen">
      <Background />
      <div className="relative z-10 flex justify-center px-4 py-16 sm:py-24">
        <Card className="w-full max-w-md p-8 gap-4 border-utd-primary/20">
          <h1 className="text-2xl font-bold text-utd-primary">Sign in to Ask Temoc</h1>
          <p className="text-sm text-muted-foreground">
            Use your UT Dallas account (@{allowedEmailDomain()}).
          </p>
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-md">
              <p className="text-red-700 text-sm">{error}</p>
            </div>
          )}
          {providerList.length === 0 ? (
            <p className="text-sm text-yellow-700">
              No sign-in provider is configured. See docs/AUTH_SETUP.md.
            </p>
          ) : (
            providerList.map((provider) => (
              <form
                key={provider.id}
                action={async () => {
                  "use server";
                  await signIn(provider.id, { redirectTo: callbackUrl });
                }}
              >
                <Button
                  type="submit"
                  className="w-full bg-utd-secondary hover:bg-utd-primary/80 text-white"
                >
                  Continue with {provider.name}
                </Button>
              </form>
            ))
          )}
        </Card>
      </div>
    </div>
  );
}

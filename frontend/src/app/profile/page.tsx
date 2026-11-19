import { redirect } from "next/navigation";
import Background from "@/components/ui/background";
import { Card } from "@/components/ui/card";
import { auth } from "@/auth";

function display(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value.length ? value.join(", ") : "Not returned";
  return value?.trim() ? value : "Not returned";
}

function Fields({
  rows,
}: {
  rows: { label: string; value: string | string[] | undefined }[];
}) {
  return (
    <dl>
      {rows.map((row) => (
        <div
          key={row.label}
          className="grid gap-1 border-b border-border/70 py-3 sm:grid-cols-[14rem_1fr]"
        >
          <dt className="text-sm text-muted-foreground">{row.label}</dt>
          <dd className="text-sm break-all">{display(row.value)}</dd>
        </div>
      ))}
    </dl>
  );
}

export default async function ProfilePage() {
  const session = await auth();
  if (!session?.user) redirect("/signin?callbackUrl=/profile");

  const entra = session.entra;
  const graph = session.graph;
  const heading =
    graph?.displayName ?? entra?.name ?? session.user.name ?? session.user.email ?? "Profile";

  return (
    <div className="relative min-h-screen">
      <Background />
      <div className="relative z-10 mx-auto flex max-w-3xl flex-col gap-6 px-4 py-10">
        <div>
          <h1 className="text-3xl font-bold text-utd-primary">{heading}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Fields from the Microsoft sign-in token and from Microsoft Graph.
          </p>
        </div>

        {!entra && !graph && (
          <Card className="border-utd-primary/20 p-6">
            <p className="text-sm">
              This session has no Microsoft profile yet. Sign out and sign in with
              Microsoft to load it.
            </p>
          </Card>
        )}

        {session.graphError && (
          <Card className="border-red-200 bg-red-50 p-6">
            <p className="text-sm text-red-700">
              Microsoft Graph did not return a profile: {session.graphError}
            </p>
          </Card>
        )}

        <Card className="border-utd-primary/20 px-6 py-2">
          <h2 className="pt-4 text-lg font-semibold">OpenID</h2>
          <p className="text-xs text-muted-foreground">Scope: openid</p>
          <Fields
            rows={[
              { label: "Subject", value: entra?.sub },
              { label: "Tenant ID", value: entra?.tid },
            ]}
          />
        </Card>

        <Card className="border-utd-primary/20 px-6 py-2">
          <h2 className="pt-4 text-lg font-semibold">Profile</h2>
          <p className="text-xs text-muted-foreground">Scope: profile</p>
          <Fields
            rows={[
              { label: "Name", value: entra?.name },
              { label: "Given name", value: entra?.given_name },
              { label: "Family name", value: entra?.family_name },
              { label: "Preferred username", value: entra?.preferred_username },
              { label: "Object ID", value: entra?.oid },
            ]}
          />
        </Card>

        <Card className="border-utd-primary/20 px-6 py-2">
          <h2 className="pt-4 text-lg font-semibold">Email</h2>
          <p className="text-xs text-muted-foreground">Scope: email</p>
          <Fields rows={[{ label: "Email", value: entra?.email }]} />
        </Card>

        <Card className="border-utd-primary/20 px-6 py-2">
          <h2 className="pt-4 text-lg font-semibold">Microsoft Graph</h2>
          <p className="text-xs text-muted-foreground">Permission: User.Read</p>
          <Fields
            rows={[
              { label: "ID", value: graph?.id },
              { label: "Display name", value: graph?.displayName },
              { label: "Given name", value: graph?.givenName },
              { label: "Surname", value: graph?.surname },
              { label: "Mail", value: graph?.mail },
              { label: "User principal name", value: graph?.userPrincipalName },
              { label: "Job title", value: graph?.jobTitle },
              { label: "Mobile phone", value: graph?.mobilePhone },
              { label: "Office location", value: graph?.officeLocation },
              { label: "Preferred language", value: graph?.preferredLanguage },
              { label: "Business phones", value: graph?.businessPhones },
            ]}
          />
        </Card>
      </div>
    </div>
  );
}

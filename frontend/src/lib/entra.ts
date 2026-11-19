/**
 * Fields the app is allowed to read.
 *
 * - openid: subject of the ID token
 * - profile: name, given/family name, preferred username, object id
 * - email: email address
 * - User.Read: Microsoft Graph GET /me default profile
 */

export type EntraIdClaims = {
  sub?: string;
  tid?: string;
  oid?: string;
  name?: string;
  given_name?: string;
  family_name?: string;
  preferred_username?: string;
  email?: string;
};

export type GraphUser = {
  id?: string;
  displayName?: string;
  givenName?: string;
  surname?: string;
  mail?: string;
  userPrincipalName?: string;
  jobTitle?: string;
  mobilePhone?: string;
  officeLocation?: string;
  preferredLanguage?: string;
  businessPhones?: string[];
};

const ID_CLAIM_KEYS = [
  "sub",
  "tid",
  "oid",
  "name",
  "given_name",
  "family_name",
  "preferred_username",
  "email",
] as const;

export function claimsFromProfile(profile: unknown): EntraIdClaims {
  if (!profile || typeof profile !== "object") return {};
  const source = profile as Record<string, unknown>;
  const claims: EntraIdClaims = {};
  for (const key of ID_CLAIM_KEYS) {
    const value = source[key];
    if (typeof value === "string" && value.trim()) claims[key] = value;
  }
  return claims;
}

const GRAPH_ME =
  "https://graph.microsoft.com/v1.0/me?$select=id,displayName,givenName,surname,mail,userPrincipalName,jobTitle,mobilePhone,officeLocation,preferredLanguage,businessPhones";

export async function graphUser(
  accessToken: string,
): Promise<{ user?: GraphUser; error?: string }> {
  let response: Response;
  try {
    response = await fetch(GRAPH_ME, {
      headers: { Authorization: `Bearer ${accessToken}` },
      cache: "no-store",
    });
  } catch (error) {
    return { error: error instanceof Error ? error.message : "Graph request failed" };
  }

  if (!response.ok) {
    let message = response.statusText;
    try {
      const body = (await response.json()) as { error?: { message?: string } };
      if (body.error?.message) message = body.error.message;
    } catch {
      /* keep status text */
    }
    return { error: `${response.status} ${message}` };
  }

  const body = (await response.json()) as Record<string, unknown>;
  const user: GraphUser = {};
  for (const key of [
    "id",
    "displayName",
    "givenName",
    "surname",
    "mail",
    "userPrincipalName",
    "jobTitle",
    "mobilePhone",
    "officeLocation",
    "preferredLanguage",
  ] as const) {
    const value = body[key];
    if (typeof value === "string" && value.trim()) user[key] = value;
  }
  if (Array.isArray(body.businessPhones)) {
    user.businessPhones = body.businessPhones.filter(
      (phone): phone is string => typeof phone === "string" && phone.trim().length > 0,
    );
  }
  return { user };
}

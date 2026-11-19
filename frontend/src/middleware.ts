import { auth } from "@/auth";

// Signed-out visitors to /chat are redirected to the sign-in page
// (see the `authorized` callback in auth.ts).
export default auth;

export const config = {
  matcher: ["/chat", "/chat/:path*", "/profile"],
};

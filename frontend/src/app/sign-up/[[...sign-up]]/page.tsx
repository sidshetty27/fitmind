import { SignUp } from "@clerk/nextjs";

/**
 * Sign-up route. Same optional catch-all pattern as sign-in so Clerk can handle
 * its multi-step flows (email verification, etc.) under this URL.
 */
export default function SignUpPage() {
  return (
    <main className="flex flex-1 items-center justify-center bg-zinc-950 px-6 py-16">
      <SignUp />
    </main>
  );
}

import { SignIn } from "@clerk/nextjs";

/**
 * Sign-in route. The optional catch-all segment `[[...sign-in]]` lets Clerk
 * own every sub-path it needs (e.g. /sign-in/factor-one, /sign-in/sso-callback)
 * without us defining each one.
 */
export default function SignInPage() {
  return (
    <main className="flex flex-1 items-center justify-center bg-zinc-950 px-6 py-16">
      <SignIn />
    </main>
  );
}

import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

import { TemplateForm } from "@/components/templates/TemplateForm";

export default async function NewTemplatePage() {
  const { userId } = await auth();
  if (!userId) {
    redirect("/sign-in?redirect_url=/dashboard/templates/new");
  }

  return (
    <div className="mx-auto w-full max-w-3xl">
      <header className="mb-6">
        <Link
          href="/dashboard/templates"
          className="text-xs text-zinc-500 hover:text-zinc-300"
        >
          ← Templates
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">New template</h1>
        <p className="mt-1 text-sm text-zinc-500">
          A plan you can log in one click. Only the name is required.
        </p>
      </header>

      <TemplateForm mode="create" />
    </div>
  );
}

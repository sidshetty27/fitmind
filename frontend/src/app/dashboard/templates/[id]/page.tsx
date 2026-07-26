import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { notFound, redirect } from "next/navigation";

import { api, ApiError, type WorkoutTemplate } from "@/lib/api";
import { TemplateForm } from "@/components/templates/TemplateForm";

/**
 * View and edit one template.
 *
 * Next.js 16: `params` is a Promise. A 404 means the template does not exist or
 * belongs to someone else — the backend deliberately does not distinguish.
 */
export default async function TemplateDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const { userId, getToken } = await auth();
  if (!userId) {
    redirect(`/sign-in?redirect_url=/dashboard/templates/${id}`);
  }

  const token = await getToken();

  let template: WorkoutTemplate;
  try {
    template = await api.templates.get(token, id);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) {
      notFound();
    }
    throw error;
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
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">{template.name}</h1>
        <p className="mt-1 text-sm text-zinc-500">
          {template.exercises.length}{" "}
          {template.exercises.length === 1 ? "exercise" : "exercises"}
          {template.description ? ` · ${template.description}` : ""}
        </p>
      </header>

      <TemplateForm mode="edit" initial={template} />
    </div>
  );
}

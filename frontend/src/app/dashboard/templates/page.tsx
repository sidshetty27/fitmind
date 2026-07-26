import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

import { api, type TemplateListItem } from "@/lib/api";
import { normalizeApiError } from "@/lib/apiErrors";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { TemplateRowActions } from "@/components/templates/TemplateRowActions";

/**
 * Saved workout templates (Phase 5).
 *
 * Templates are plans, so this list is alphabetical rather than chronological —
 * you arrive knowing which one you want.
 */
export default async function TemplatesPage() {
  const { userId, getToken } = await auth();
  if (!userId) {
    redirect("/sign-in?redirect_url=/dashboard/templates");
  }

  const token = await getToken();

  let templates: TemplateListItem[] = [];
  let loadError: string | null = null;

  try {
    templates = await api.templates.list(token);
  } catch (error) {
    loadError = normalizeApiError(error).formError;
  }

  return (
    <div className="mx-auto w-full max-w-4xl">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Templates</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Reusable session plans. Log one and adjust the numbers you actually hit.
          </p>
        </div>
        <Link href="/dashboard/templates/new">
          <Button size="lg">New template</Button>
        </Link>
      </header>

      {loadError && (
        <Alert className="mt-6" title="Couldn't load your templates">
          {loadError}
        </Alert>
      )}

      {!loadError && templates.length === 0 && (
        <div className="mt-6">
          <EmptyState
            title="No templates yet"
            description="Build a plan you repeat — Push Day A, Legs, whatever you run — and logging it becomes one click. You can also save any workout as a template from its page."
            action={
              <Link href="/dashboard/templates/new">
                <Button>Create your first template</Button>
              </Link>
            }
          />
        </div>
      )}

      {templates.length > 0 && (
        <Card className="mt-6">
          <ul className="divide-y divide-zinc-800">
            {templates.map((template) => (
              <li
                key={template.id}
                className="flex items-center gap-3 px-4 py-3.5 transition-colors hover:bg-zinc-800/30"
              >
                <Link
                  href={`/dashboard/templates/${template.id}`}
                  className="min-w-0 flex-1"
                >
                  <p className="truncate text-sm font-medium text-zinc-100">
                    {template.name}
                  </p>
                  <p className="mt-0.5 truncate text-xs text-zinc-500">
                    {template.exercise_count}{" "}
                    {template.exercise_count === 1 ? "exercise" : "exercises"}
                    {template.description ? ` · ${template.description}` : ""}
                  </p>
                </Link>

                <TemplateRowActions
                  templateId={template.id}
                  name={template.name}
                  exerciseCount={template.exercise_count}
                />
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

import { redirect } from "next/navigation";
import { PageHeader } from "@/components/AppShell";
import { WelcomeWizard } from "@/components/WelcomeWizard";
import { startOnboardingAction } from "@/app/welcome/actions";
import { getCurrentUser, listSavedSearches } from "@/lib/api";

export const dynamic = "force-dynamic";

// Compact starter list. Dealers can add more on /listings with filters.
const POPULAR_MAKES = [
  "Ford",
  "Chevrolet",
  "Toyota",
  "Honda",
  "Jeep",
  "Ram",
  "GMC",
  "Nissan",
  "Subaru",
  "Tesla",
  "BMW",
  "Mercedes-Benz",
];

export default async function WelcomePage() {
  // If the user already has a saved search, they've done onboarding —
  // bounce them to the real dashboard.
  const saved = await listSavedSearches().catch(() => []);
  if (saved.length > 0) {
    redirect("/");
  }

  const user = await getCurrentUser().catch(() => null);

  return (
    <div className="max-w-2xl">
      <PageHeader
        title={`Welcome${user?.name ? ", " + user.name : ""}`}
        subtitle="Tell us what you're looking for. We'll save it as a search and email you when hot leads drop."
      />

      <WelcomeWizard
        action={startOnboardingAction}
        popularMakes={POPULAR_MAKES}
      />
    </div>
  );
}

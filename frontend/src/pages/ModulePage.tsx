import { navigation } from "../navigation";
import { EmptyState, PageHeader, Panel } from "../components/UI";
export const modules = {
  "culture-library": {
    title: "Culture Library",
    description: "The biological identities behind every cultivation cycle.",
    workspace: "Your culture collection starts here.",
    features: [
      "Species and strains",
      "Genetic culture lines",
      "Spore sources",
      "Lineage relationships",
      "Culture histories",
    ],
  },
  laboratory: {
    title: "Laboratory",
    description:
      "A dedicated workspace for culture preparation and propagation.",
    workspace: "Growing Cultures",
    features: [
      "Growing agar cultures",
      "Agar preparation batches",
      "Liquid cultures",
      "Culture transfers",
      "Laboratory observations",
      "Spore germination",
    ],
  },
  cultivation: {
    title: "Cultivation",
    description: "Follow physical material from spawn preparation to harvest.",
    workspace: "A clear view of every growing cycle.",
    features: [
      "Spawn jars",
      "Spawn bags",
      "Spawn preparation",
      "Fruiting units",
      "Colonization",
      "Harvests and flushes",
    ],
  },
  inventory: {
    title: "Inventory",
    description: "Keep materials, supplies, and reusable equipment organized.",
    workspace: "Everything you need to keep growing.",
    features: [
      "Biological inventory",
      "Raw materials",
      "Consumables",
      "Reusable containers",
      "Equipment",
      "Storage locations",
      "Recipes and basic purchase costs",
    ],
  },
  reports: {
    title: "Reports",
    description: "Turn cultivation history into useful insight.",
    workspace: "Your data will tell the story.",
    features: [
      "Cultivation progress",
      "Colonization times",
      "Harvest yields",
      "Culture performance",
      "Contamination statistics",
      "Inventory usage",
    ],
  },
};
export default function ModulePage({
  module,
}: {
  module: keyof typeof modules;
}) {
  const info = modules[module];
  const Icon = navigation.find((item) => item.title === info.title)!.icon;
  return (
    <>
      <PageHeader title={info.title} description={info.description} />
      <div className="module-intro">
        <span className="badge">PLANNED WORKSPACE</span>
        <p>
          This section is part of a future milestone. Record creation is not
          available yet.
        </p>
      </div>
      <Panel
        title={
          module === "laboratory"
            ? "Growing Cultures"
            : `${info.title} Workspace`
        }
        icon={Icon}
      >
        <EmptyState
          icon={Icon}
          title={info.workspace}
          description="The application foundation is in place. This workspace will expand as the next modules are introduced."
        />
      </Panel>
      <div className="section-heading">
        <h2>Built for what comes next</h2>
        <span>FUTURE CAPABILITIES</span>
      </div>
      <div className="feature-grid">
        {info.features.map((feature, i) => (
          <div className="feature-item" key={feature}>
            <span className="feature-number">
              {String(i + 1).padStart(2, "0")}
            </span>
            <h3>{feature}</h3>
          </div>
        ))}
      </div>
    </>
  );
}

import { Link } from "react-router-dom";
import { PackagePlus, Dna, Boxes } from "lucide-react";
import { PageHeader, Panel } from "../components/UI";
export default function Inventory() {
  return (
    <>
      <PageHeader
        title="Inventory"
        description="Bring outside material into your collection. Supplies, recipes, purchases, and stock management will expand here in later stages."
      />
      <Panel
        title="Receive outside material"
        icon={PackagePlus}
        label="ACQUISITIONS"
      >
        <div className="workflow-source">
          <p>
            Register purchased, gifted, or otherwise acquired cultures, spores,
            spawn, or ready-to-fruit material. Start at the stage you received
            it; earlier history stays unknown.
          </p>
          <Link className="button primary" to="/inventory/receive-acquisition">
            Receive Acquisition
          </Link>
          <p>
            For preparation, inoculation, or transfers within your collection,
            use Dashboard Quick Create. Acquisition is not a substitute for
            those operations.
          </p>
        </div>
      </Panel>
      <Panel title="Strain management" icon={Dna}>
        <div className="workflow-source">
          <p>Manage reference identities without creating physical material.</p>
          <Link className="button" to="/inventory/strains/new">
            Add Strain
          </Link>
          <Link className="button" to="/culture-library">
            Browse catalog
          </Link>
        </div>
      </Panel>
      <Panel title="Stock and supplies" icon={Boxes} label="PLANNED">
        <div className="workflow-source">
          <p>
            Recipes, preparation batches, reusable container pools, known stock
            balances, automatic deductions, and purchase tracking are planned
            for subsequent stages. No stock balance is implied by registered
            starting quantities.
          </p>
        </div>
      </Panel>
    </>
  );
}
